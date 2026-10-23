# Guide de l'API pour le frontend

Documentation interactive (toujours à jour, avec bouton « Try it out ») :

- Swagger : <http://localhost:8000/api/docs/>
- ReDoc : <http://localhost:8000/api/redoc/>
- Schéma OpenAPI : <http://localhost:8000/api/schema/> (copie dans [`openapi.yaml`](openapi.yaml))

> Astuce : on peut générer un client TypeScript typé à partir du schéma, par exemple
> `npx openapi-typescript http://localhost:8000/api/schema/ -o src/api/schema.d.ts`.

Toutes les URL commencent par `/api/`. Le format est JSON, sauf l'import de fichier
(`multipart/form-data`) et les exports (`text/csv`).

---

## 1. Conventions

### Authentification (JWT)

```
POST /api/auth/login/      {"username": "caissier1", "password": "..."}
→ 200 {"access": "...", "refresh": "...", "user": {...profil + capabilities...}}
```

Envoyer ensuite sur **chaque** requête : `Authorization: Bearer <access>`.

| Token | Durée (par défaut) | Usage |
|---|---|---|
| `access` | 30 min (`JWT_ACCESS_MINUTES`) | En-tête `Authorization` |
| `refresh` | 7 jours (`JWT_REFRESH_DAYS`) | `POST /api/auth/refresh/ {"refresh": "..."}` → nouveaux `access` **et** `refresh` |

Flux recommandé dans la PWA :

1. Sur une réponse `401`, appeler `/api/auth/refresh/` **une seule fois**, remplacer
   les deux tokens (le refresh tourne : l'ancien est révoqué), puis rejouer la requête.
2. Si le refresh échoue aussi (`401`) → retour à l'écran de connexion.
3. Déconnexion : `POST /api/auth/logout/ {"refresh": "..."}` puis effacer les tokens.
4. Si `user.must_change_password` vaut `true` → afficher l'écran de changement de mot de passe
   (`POST /api/auth/change-password/`, qui renvoie de nouveaux tokens).

La connexion est limitée à 10 tentatives par minute (`429 Too Many Requests` au-delà).

### Pagination

Les listes sont paginées : `?page=2&page_size=50` (25 par défaut, 200 maximum).

```json
{"count": 132, "next": "http://…?page=3", "previous": "http://…?page=1", "results": [ … ]}
```

Exceptions non paginées (listes courtes) : `/api/sizes/`, `/api/colors/`, `/api/age-ranges/`,
`/api/categories/tree/`.

### Recherche, filtres, tri

- `?search=robe` : recherche texte (nom, référence, SKU, code-barres… selon l'endpoint).
- Filtres : `?category=3&gender=GIRL&stock_status=LOW` (liste par endpoint ci-dessous et dans Swagger).
- Tri : `?ordering=-created_at` (le `-` inverse l'ordre).
- Dates : format `AAAA-MM-JJ` (`date_from`, `date_to`, bornes incluses).

### Montants

- Dans les objets (articles, ventes…), les montants sont des **chaînes** : `"10000.00"`.
  Les convertir avec `Number()` pour l'affichage, ne jamais recalculer un total côté client.
- Dans les rapports et le tableau de bord, ce sont des **nombres** : `28500.0`.
- La devise est donnée par `GET /api/health/` (`"currency": "XOF"`).

### Erreurs

| Code | Signification | Corps |
|---|---|---|
| `400` | Données invalides ou règle métier (stock insuffisant, remise trop élevée…) | `{"champ": ["message"]}` ou `{"detail": "message"}` |
| `401` | Non connecté / token expiré | `{"detail": "…", "code": "token_not_valid"}` |
| `403` | Connecté mais pas le droit | `{"detail": "Cette action est réservée à l'administrateur."}` |
| `404` | Introuvable (ou pas visible pour cet utilisateur) | `{"detail": "…"}` |
| `405` | Action impossible (ex. supprimer une vente) | |
| `409` | Suppression impossible : élément utilisé (→ archiver) | `{"detail": "…"}` |
| `429` | Trop de tentatives de connexion | |

Les messages sont en français et peuvent être affichés tels quels à l'utilisateur.
Pour un `400`, afficher chaque message sous le champ correspondant ; `detail`,
`lines` et `non_field_errors` sont des messages généraux.

### Exports CSV

Ajouter `?export=csv` aux endpoints de rapport et d'historique : le serveur renvoie un
fichier `.csv` (séparateur `;`, UTF-8 avec BOM : s'ouvre directement dans Excel).
Les mêmes filtres que la version JSON s'appliquent. Avec `fetch`, récupérer un `Blob`
(en gardant l'en-tête `Authorization`) puis déclencher le téléchargement.

---

## 2. Endpoints

Légende : 👤 tout utilisateur connecté · 🔑 administrateur uniquement.

### Authentification et comptes

| Méthode | URL | Accès | Rôle |
|---|---|---|---|
| POST | `/api/auth/login/` | public | Connexion |
| POST | `/api/auth/refresh/` | public | Renouveler les tokens |
| POST | `/api/auth/logout/` | 👤 | Déconnexion |
| GET | `/api/auth/me/` | 👤 | Profil + `capabilities` |
| POST | `/api/auth/change-password/` | 👤 | `{"old_password", "new_password"}` |
| GET/POST | `/api/users/` | 🔑 | Lister / créer un compte (`username`, `full_name`, `role`, `password`, `phone`) |
| GET/PATCH | `/api/users/{id}/` | 🔑 | Détail / modifier (pas de suppression) |
| POST | `/api/users/{id}/reset-password/` | 🔑 | `{"new_password"}` |
| POST | `/api/users/{id}/deactivate/` · `/activate/` | 🔑 | Bloquer / débloquer un compte |

### Catalogue

| Méthode | URL | Accès | Rôle |
|---|---|---|---|
| GET | `/api/categories/` · `/api/categories/tree/` | 👤 | Catégories (liste ou arbre à 2 niveaux) |
| POST/PATCH/DELETE | `/api/categories/…` | 🔑 | Gérer les catégories |
| GET | `/api/age-ranges/` · `/api/sizes/` · `/api/colors/` | 👤 | Référentiels (écriture 🔑) |
| CRUD | `/api/suppliers/` | 🔑 | Fournisseurs |
| GET | `/api/articles/` | 👤 | Articles avec variantes et stock total |
| POST | `/api/articles/` | 🔑 | Créer un article (+ variantes et stock initial, voir exemple) |
| GET/PATCH | `/api/articles/{id}/` | 👤 / 🔑 | Fiche / modification |
| DELETE | `/api/articles/{id}/` | 🔑 | Seulement si jamais mouvementé, sinon `409` |
| POST | `/api/articles/{id}/archive/` · `/restore/` | 🔑 | Archiver / désarchiver |
| POST | `/api/articles/import/` | 🔑 | Import Excel / CSV (voir §3.5) |
| GET | `/api/articles/import-template/` | 🔑 | Modèle de fichier d'import |
| GET | `/api/variants/` | 👤 | Variantes (taille × couleur) avec quantité |
| POST/PATCH | `/api/variants/…` | 🔑 | Ajouter / modifier une variante (la quantité n'est jamais modifiable ici) |
| GET | `/api/variants/lookup/?code=…` | 👤 | Recherche exacte par code-barres ou SKU (scanner) |
| GET | `/api/variants/low-stock/` | 👤 | Variantes à réapprovisionner |

**Filtres `/api/articles/`** : `category` (inclut les sous-catégories), `article_type`, `gender`,
`age_range`, `age_months` (ex. `30` = enfant de 2 ans ½), `brand`, `supplier`, `min_price`,
`max_price`, `stock_status` (`OUT`, `LOW`, `OK`, `AVAILABLE`), `is_regulated`, `is_archived`.

**Filtres `/api/variants/`** : `article`, `size`, `color`, `category`, `article_type`, `gender`,
`stock_status`, `barcode`, `sku`, `is_active`, `include_archived`.

**Valeurs fixes**

| Champ | Valeurs |
|---|---|
| `article_type` | `CLOTHING` Vêtement, `UNDERWEAR` Sous-vêtement, `SHOES` Chaussures, `ACCESSORY` Accessoire, `CHILDCARE` Puériculture et sommeil, `FEEDING` Repas, `HYGIENE` Hygiène, `SAFETY` Sorties et sécurité, `TOY` Jouet |
| `gender` | `GIRL` Fille, `BOY` Garçon, `UNISEX` Mixte |
| `stock_status` | `OUT` rupture, `LOW` ≤ seuil d'alerte, `OK` disponible |
| `payment_method` | `CASH` Espèces, `MOBILE_MONEY`, `CARD`, `BANK_TRANSFER`, `OTHER` |

Chaque réponse contient aussi le libellé français (`gender_label`, `article_type_label`…) :
inutile de traduire côté frontend.

### Stock

| Méthode | URL | Accès | Rôle |
|---|---|---|---|
| GET | `/api/stock-movements/` | 👤 | Historique (filtres : `variant`, `article`, `category`, `movement_type`, `user`, `sale`, `lot_number`, `direction=in/out`, `date_from`, `date_to`, `export=csv`) |
| POST | `/api/stock-movements/` | 🔑 | Un mouvement : `{"variant", "movement_type", "quantity", "reason", "lot_number", "unit_cost"}` |
| POST | `/api/stock-movements/reception/` | 🔑 | Une livraison complète : `{"reason", "lines": [{"variant", "quantity", "lot_number", "unit_cost"}]}` |
| POST | `/api/stock-movements/inventory-count/` | 🔑 | Inventaire : `{"variant", "counted_quantity", "reason"}` → le serveur crée l'ajustement |

Types saisissables : `PURCHASE` (réception), `CUSTOMER_RETURN`, `ADJUST_IN`, `ADJUST_OUT`,
`LOSS` (perte/casse/vol), `SUPPLIER_RETURN`. Les types `SALE` et `SALE_CANCEL` sont créés
automatiquement par les ventes. Un motif (`reason`) est obligatoire sauf pour `PURCHASE`.
Pour un article réglementé (`is_regulated`), `lot_number` est obligatoire à la réception.

### Ventes

| Méthode | URL | Accès | Rôle |
|---|---|---|---|
| GET | `/api/sales/` | 👤 | Ventes (les siennes pour un caissier). Filtres : `status`, `cashier`, `payment_method`, `number`, `date_from`, `date_to`, `min_total`, `max_total`, `has_discount`, `article`, `variant`, `export=csv` |
| POST | `/api/sales/` | 👤 | Enregistrer une vente (voir §3.1) |
| GET | `/api/sales/{id}/` | 👤 | Détail / ticket de caisse |
| POST | `/api/sales/{id}/cancel/` | 🔑 | `{"reason"}` → annule et remet en stock |

### Comptes rendus de caisse

| Méthode | URL | Accès | Rôle |
|---|---|---|---|
| GET | `/api/cash-reports/preview/?date=AAAA-MM-JJ` | 👤 | Chiffres de sa journée avant envoi |
| POST | `/api/cash-reports/` | 👤 | `{"counted_cash", "comment", "report_date"?}` |
| PATCH | `/api/cash-reports/{id}/` | 👤 (auteur) | Corriger tant que non vérifié |
| GET | `/api/cash-reports/` | 👤 | Les siens (tous pour l'admin) |
| POST | `/api/cash-reports/{id}/review/` | 🔑 | `{"admin_comment"}` → statut `REVIEWED` |

### Tableau de bord et rapports

Paramètres communs de période : `period` = `today` (défaut), `yesterday`, `week` (7 derniers jours),
`month`, `last_month`, `year`, `custom` (avec `date_from` et `date_to`).

| Méthode | URL | Accès | Contenu |
|---|---|---|---|
| GET | `/api/dashboard/summary/` | 👤 | CA, nombre de ventes, panier moyen, remises, annulations, paiements, top 5, stock, alertes, 5 dernières ventes, notifications non lues |
| GET | `/api/reports/sales/` | 👤 | Totaux + série par jour ou mois (`group_by=day/month`), filtres `cashier`, `payment_method` |
| GET | `/api/reports/top-articles/` | 👤 | Articles les plus vendus (`limit`, `category`) |
| GET | `/api/reports/stock/` | 👤 | Unités, ruptures, valeur du stock, répartition par catégorie (CSV : une ligne par variante) |
| GET | `/api/reports/cashiers/` | 👤 | Ventes par caissier (un caissier ne voit que sa ligne) |

Tous acceptent `?export=csv`. Les marges (`gross_margin`) et la valeur au prix d'achat
(`stock_value_cost`) ne sont renvoyées qu'à l'administrateur.

### Notifications et audit

| Méthode | URL | Accès | Rôle |
|---|---|---|---|
| GET | `/api/notifications/` | 👤 | Ses notifications (`is_read`, `type`, `level`) |
| GET | `/api/notifications/unread-count/` | 👤 | `{"unread": 3}` — à interroger toutes les 30–60 s |
| POST | `/api/notifications/{id}/mark-read/` | 👤 | Marquer comme lue |
| POST | `/api/notifications/mark-all-read/` | 👤 | Tout marquer comme lu |
| GET | `/api/audit-logs/` | 🔑 | Journal (filtres `user`, `action`, `target_type`, `target_id`, `date_from`, `date_to`) |
| GET | `/api/health/` | public | État de l'API, nom de la boutique, devise |

Types de notification : `SALE`, `SALE_CANCELLED`, `LOW_STOCK`, `OUT_OF_STOCK`, `CASH_REPORT`,
`SENSITIVE_ACTION`. Niveaux : `info`, `warning`, `danger`. Le champ `data` contient les
identifiants utiles pour ouvrir le bon écran (`sale_id`, `variant_id`, `cash_report_id`…).

---

## 3. Exemples

### 3.1 Enregistrer une vente (écran caisse)

```http
POST /api/sales/
Authorization: Bearer <access>
Content-Type: application/json

{
  "client_request_id": "7d0c3c39-5d0b-4a5e-9a0f-1b2c3d4e5f60",
  "payment_method": "CASH",
  "amount_received": "20000",
  "customer_name": "",
  "lines": [
    {"variant": 8, "quantity": 2},
    {"variant": 15, "quantity": 1, "discount_amount": "500", "discount_reason": "Petit défaut"}
  ]
}
```

Réponse `201` :

```json
{
  "id": 42, "number": "V20261023-00042", "status": "COMPLETED", "status_label": "Validée",
  "cashier": 2, "cashier_name": "Aminata K.", "payment_method": "CASH", "payment_method_label": "Espèces",
  "subtotal": "19500.00", "discount_total": "500.00", "total": "19000.00",
  "amount_received": "20000.00", "change_due": "1000.00", "items_count": 3,
  "lines": [
    {"id": 90, "variant": 8, "article_name": "Robe à volants", "variant_label": "Robe à volants (4A / Rose)",
     "sku": "ROB-001-4A-ROS", "quantity": 2, "unit_price": "9000.00", "discount_amount": "0.00",
     "discount_reason": "", "line_total": "18000.00"}
  ],
  "created_at": "2026-10-23T16:40:12.511Z"
}
```

Règles à connaître :

- **Les prix viennent du serveur.** Le frontend n'envoie jamais de prix ; il affiche
  `effective_price` des variantes pour l'aperçu, puis le total renvoyé par le serveur.
- **`client_request_id`** : générer un UUID (`crypto.randomUUID()`) à l'ouverture du panier et le
  garder jusqu'au succès. En cas de coupure réseau, renvoyer la même requête : la réponse `200`
  contient la vente déjà enregistrée, sans doublon. Nouveau panier = nouvel UUID.
- **Tout ou rien** : si un seul article manque (`400 Stock insuffisant…`), rien n'est enregistré.
- **Remise** : en montant par ligne, `discount_reason` obligatoire ; un caissier est limité à
  `CASHIER_MAX_DISCOUNT_PERCENT` % du montant de la ligne.
- `amount_received` est facultatif ; s'il est fourni, il doit couvrir le total, et pour `CASH`
  le serveur calcule `change_due` (la monnaie à rendre).
- Mobile Money / carte : renseigner `payment_reference` (numéro de transaction).

### 3.2 Scanner un code-barres

```http
GET /api/variants/lookup/?code=3700000000011
→ 200 {"id": 8, "label": "Robe à volants (4A / Rose)", "sku": "…", "effective_price": "9000.00",
       "quantity": 7, "stock_status": "OK", …}
→ 404 {"detail": "Aucun article ne correspond à ce code."}
```

### 3.3 Créer un article avec ses variantes (admin)

```json
POST /api/articles/
{
  "name": "Robe à volants", "reference": "ROB-001", "category": 12,
  "article_type": "CLOTHING", "gender": "GIRL", "age_ranges": [7, 8],
  "purchase_price": "4500", "sale_price": "9000", "brand": "Petit Soleil",
  "initial_variants": [
    {"size": 11, "color": 7, "initial_quantity": 5, "barcode": "3700000000011"},
    {"size": 13, "color": 7, "initial_quantity": 3, "alert_threshold": 1}
  ]
}
```

L'image se charge en `multipart/form-data` (champ `image`), par exemple via
`PATCH /api/articles/{id}/` après la création. Un article réglementé
(`is_regulated: true`, jouets, biberons…) exige `safety_standard`, et un `lot_number`
pour chaque `initial_quantity`.

### 3.4 Réceptionner une livraison (admin)

```json
POST /api/stock-movements/reception/
{"reason": "Livraison Fournisseur X – BL 2026-118",
 "lines": [{"variant": 8, "quantity": 12}, {"variant": 31, "quantity": 6, "lot_number": "L2410"}]}
```

### 3.5 Importer un fichier Excel ou CSV (admin)

1. `GET /api/articles/import-template/` → modèle CSV (colonnes : `reference`, `nom`, `categorie`,
   `type`, `genre`, `tranches_age`, `marque`, `prix_achat`, `prix_vente`, `taille`, `couleur`,
   `code_barres`, `quantite`, `seuil_alerte`, `numero_lot`).
2. Vérifier sans rien enregistrer : `POST /api/articles/import/` (multipart, `file` + `dry_run=true`).
3. Importer : même appel sans `dry_run`.

```json
{"dry_run": false, "success": true, "rows": 40, "errors": [],
 "articles_created": 12, "articles_updated": 3, "variants_created": 38, "units_added": 214}
```

En cas d'erreur (`400`), **rien n'est enregistré** et `errors` liste les lignes à corriger :
`[{"line": 7, "error": "catégorie « Robe » introuvable"}]`.

### 3.6 Tableau de bord

```http
GET /api/dashboard/summary/?period=month
```

```json
{
  "period": {"start": "2026-10-01", "end": "2026-10-23", "label": "Mois en cours"},
  "currency": "XOF",
  "sales": {"revenue": 28500.0, "sales_count": 3, "items_sold": 5, "average_basket": 9500.0,
            "discounts_total": 500.0, "cancelled_count": 0, "cancelled_amount": 0.0, "gross_margin": 15200.0},
  "my_sales": {"revenue": 9000.0, "sales_count": 1, "…": "…"},
  "by_payment_method": [{"payment_method": "CASH", "label": "Espèces", "sales_count": 2, "amount": 23000.0}],
  "top_articles": [{"article_id": 2, "reference": "ROB-001", "name": "Robe à volants",
                    "category": "Robes", "quantity_sold": 3, "revenue": 27000.0, "sales_count": 2}],
  "stock": {"articles_count": 6, "variants_count": 26, "units_in_stock": 98, "out_of_stock_count": 0,
            "low_stock_count": 9, "stock_value_sale": 736000.0, "stock_value_cost": 330000.0},
  "stock_alerts": [{"variant_id": 20, "label": "Baskets à scratch (24 / Blanc)", "quantity": 2, "…": "…"}],
  "recent_sales": ["…5 dernières ventes…"],
  "unread_notifications": 4
}
```

---

## 4. Conseils pour la PWA

- **Hors ligne** : mettre en cache (service worker) le catalogue (`/api/articles/`, `/api/variants/`,
  référentiels) pour la consultation. Les ventes faites hors ligne peuvent être mises en file
  d'attente avec leur `client_request_id`, puis envoyées au retour du réseau : il n'y aura pas de
  doublon. Le serveur reste juge du stock : une vente envoyée plus tard peut être refusée
  (`400 Stock insuffisant`), il faut alors prévenir le caissier.
- **Simplicité** : les libellés (`*_label`) et les messages d'erreur sont déjà rédigés en français.
- **Droits** : construire les menus à partir de `user.capabilities` (voir [PERMISSIONS.md](PERMISSIONS.md)).
- **CORS** : ajouter l'adresse du frontend dans `CORS_ALLOWED_ORIGINS` du `.env`
  (en développement, `localhost:5173`, `3000`, `4200` et `8080` sont autorisés par défaut).
