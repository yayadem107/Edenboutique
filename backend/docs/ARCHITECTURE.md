# Architecture du backend

```
Frontend PWA (mobile · tablette · ordinateur)
        │  HTTPS + JSON, en-tête Authorization: Bearer <JWT>
        ▼
Django REST Framework ── authentification · permissions · règles métier
        │  transactions + verrous de ligne
        ▼
PostgreSQL ── données, historiques, contraintes d'intégrité
```

Le frontend ne calcule rien d'important : prix, totaux, remises, stock et
statistiques sont toujours calculés et vérifiés par le serveur.

## Organisation des dossiers

```
backend/
├── config/
│   ├── settings/
│   │   ├── base.py          réglages communs (lus depuis .env)
│   │   ├── development.py   poste du développeur / Docker Compose
│   │   ├── production.py    serveur en ligne (HTTPS, sécurité)
│   │   └── test.py          tests automatisés (choisi automatiquement par `manage.py test`)
│   └── urls.py              toutes les routes /api/...
├── apps/
│   ├── common/         outils partagés : permissions, pagination, erreurs, export CSV, /health, seed_demo
│   ├── accounts/       utilisateurs, rôles, connexion JWT, mots de passe
│   ├── catalog/        catégories, tranches d'âge, tailles, couleurs, fournisseurs, articles, variantes, import
│   ├── inventory/      mouvements de stock (seul endroit où la quantité change)
│   ├── sales/          ventes, lignes, annulations, comptes rendus de caisse
│   ├── dashboard/      tableau de bord et rapports (aucun modèle, uniquement des calculs)
│   ├── notifications/  alertes in-app (ventes, stock faible, ruptures…)
│   └── audit/          journal « qui a fait quoi et quand »
├── tests/              tests automatisés (un fichier par module)
├── docs/               cette documentation + openapi.yaml
├── docker/entrypoint.sh  migrations + données de référence au démarrage du conteneur
├── Dockerfile · docker-compose.yml · requirements.txt · .env.example
```

Chaque application suit la même structure :

| Fichier | Contenu |
|---|---|
| `models.py` | Tables de la base |
| `services.py` | **Règles métier** (à lire en premier pour comprendre un module) |
| `serializers.py` | Validation des données reçues et format JSON des réponses |
| `views.py` | Endpoints, permissions, documentation Swagger |
| `filters.py` | Filtres de liste (`?category=…`) |
| `urls.py` | Routes |
| `admin.py` | Interface `/admin/` |

## Modèle de données

```
User (accounts) ── role: ADMIN | CASHIER
  │
Category ─┐ (2 niveaux : principale › sous-catégorie)
AgeRange ─┼──< Article >── Supplier
          │       │ 1..n
Size ─────┼──< ArticleVariant  (taille × couleur, SKU, code-barres, quantity, seuil d'alerte)
Color ────┘       │
                  ├──< StockMovement   (journal immuable : avant / après / motif / lot / utilisateur)
                  └──< SaleLine >── Sale (numéro, caissier, paiement, remises, statut)
                                     └── CashReport (compte rendu journalier du caissier)
Notification ── destinataire (User)
AuditLog     ── utilisateur, action, objet, détails, IP
```

Choix importants :

- **Article / Variante** : l'article porte les informations communes (nom, prix, catégorie, âges,
  sécurité) ; la variante (taille × couleur) porte le stock, le SKU et le code-barres. Une variante
  peut avoir un prix spécifique (`price_override`).
- **Catégorie, âge, taille et type sont indépendants** : une robe rose 4 ans est la catégorie
  « Vêtements fille › Robes », la tranche « 4–6 ans », la taille « 4A », la couleur « Rose ». On
  évite ainsi des centaines de catégories. Les tailles réelles restent distinctes de l'âge.
- **Produits réglementés** (`is_regulated`) : jouets, biberons, articles de sécurité… Norme
  (`safety_standard`) obligatoire, numéro de lot obligatoire à chaque réception : on retrouve
  quels lots ont été reçus et vendus (`/api/stock-movements/?lot_number=…`). Les
  caractéristiques propres à chaque produit vont dans `attributes` (JSON libre).
- **Archivage plutôt que suppression** : un article vendu ne peut pas être supprimé (`409`) ;
  on l'archive. Les comptes utilisateurs se désactivent, ils ne se suppriment pas.
- **Copies dans les lignes de vente** : nom, SKU, prix de vente et prix d'achat sont copiés au
  moment de la vente, pour que l'historique et les marges restent justes si le catalogue change.

## Garanties sur le stock et les ventes

1. La quantité n'est modifiée **que** par `apps/inventory/services.py::apply_movement()`.
   Le champ n'est pas modifiable dans l'API ni dans `/admin/`.
2. Chaque modification verrouille la ligne de la variante (`SELECT … FOR UPDATE`) : deux caisses
   qui vendent la dernière pièce en même temps → une seule vente passe
   (`tests/test_concurrency.py`).
3. Le stock négatif est refusé par le code **et** par une contrainte PostgreSQL (`CHECK quantity >= 0`).
4. Une vente (`apps/sales/services.py::create_sale`) est une seule transaction : lignes, mouvements
   de stock et totaux sont enregistrés ensemble, ou pas du tout.
5. Doubles soumissions : le `client_request_id` (UUID unique) envoyé par le frontend garantit
   qu'une vente renvoyée deux fois n'est enregistrée qu'une fois.
6. Une vente ne se modifie pas : l'administrateur l'annule avec un motif, ce qui remet les
   articles en stock par des mouvements `SALE_CANCEL`.
7. Mouvements de stock et journal d'audit sont en ajout seul (modification et suppression
   impossibles, y compris dans `/admin/`).

## Notifications

Créées par le serveur pour les administrateurs :

| Événement | Type | Niveau |
|---|---|---|
| Nouvelle vente (désactivable : `NOTIFY_ADMIN_ON_SALE`) | `SALE` | info |
| Vente annulée | `SALE_CANCELLED` | warning |
| Une variante passe sous son seuil d'alerte | `LOW_STOCK` | warning |
| Une variante tombe à 0 | `OUT_OF_STOCK` | danger |
| Compte rendu de caisse envoyé | `CASH_REPORT` | info, ou warning s'il y a un écart |
| Compte désactivé | `SENSITIVE_ACTION` | warning |

Les alertes de stock ne sont émises qu'au **moment où le seuil est franchi** (pas à chaque vente).
Le frontend interroge `/api/notifications/unread-count/`. Des notifications push (Web Push) ou
par e-mail / WhatsApp pourront être ajoutées dans `apps/notifications/services.py::notify_admins`.

## Journal d'audit

`apps/audit/services.py::log_action()` enregistre : connexions (réussies et échouées),
déconnexions, changements de mot de passe, créations / modifications / suppressions /
archivages (via `AuditedViewSetMixin`), mouvements de stock, imports, ventes, annulations et
comptes rendus de caisse, avec l'utilisateur, l'adresse IP et le navigateur.

## Réglages métier (`.env`)

| Variable | Défaut | Effet |
|---|---|---|
| `MAX_ACTIVE_CASHIERS` | 3 | Nombre maximum de caissiers actifs |
| `CASHIER_MAX_DISCOUNT_PERCENT` | 20 | Remise maximale d'un caissier par ligne |
| `CASHIERS_SEE_ALL_SALES` | False | Un caissier voit-il les ventes des autres ? |
| `NOTIFY_ADMIN_ON_SALE` | True | Notifier l'admin à chaque vente |
| `CURRENCY` | XOF | Devise affichée |
| `TIME_ZONE` | Africa/Abidjan | Fuseau utilisé pour « aujourd'hui », les rapports et la numérotation des ventes |

## Ajouter une fonctionnalité

1. Modèle dans `models.py`, puis `python manage.py makemigrations` et `migrate`.
2. Règle métier dans `services.py` (jamais directement dans la vue).
3. Serializer + vue + route, avec `permission_classes` explicites.
4. Test dans `tests/`, puis `python manage.py test`.
5. Mettre à jour `docs/` et régénérer `docs/openapi.yaml` :
   `python manage.py spectacular --file docs/openapi.yaml`.
