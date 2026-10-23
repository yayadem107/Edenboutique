# Permissions

Les permissions sont **appliquées par le backend**. Le frontend peut masquer
des boutons pour le confort, mais une requête interdite renvoie toujours
`403 Forbidden`, même si quelqu'un l'envoie à la main.

## Rôles

| Rôle | Code | Nombre | Comment le créer |
|---|---|---|---|
| Super administrateur | `ADMIN` | 1 (ou plus) | `python manage.py createsuperuser` |
| Caissier | `CASHIER` | 3 actifs maximum (`MAX_ACTIVE_CASHIERS`) | L'admin, via `POST /api/users/` |

Il n'y a **aucune inscription publique**. Un compte créé ou réinitialisé par
l'administrateur a `must_change_password = true` : le frontend doit alors
afficher l'écran « Choisissez votre mot de passe » (`POST /api/auth/change-password/`).

## Matrice des droits

| Action | Admin | Caissier | Endpoint(s) |
|---|---|---|---|
| Consulter les articles et le stock | ✅ | ✅ | `GET /api/articles/`, `/api/variants/`, `/api/stock-movements/` |
| Voir les prix d'achat, marges, valeur du stock au coût | ✅ | ❌ (champs retirés de la réponse) | — |
| Ajouter / modifier un article ou une variante | ✅ | ❌ | `POST/PATCH /api/articles/`, `/api/variants/` |
| Archiver / supprimer un article | ✅ | ❌ | `POST /api/articles/{id}/archive/`, `DELETE` |
| Gérer catégories, tailles, couleurs, tranches d'âge | ✅ | ❌ (lecture seule) | `/api/categories/` … |
| Gérer les fournisseurs | ✅ | ❌ | `/api/suppliers/` |
| Modifier les quantités de stock | ✅ | ❌ | `POST /api/stock-movements/`, `reception/`, `inventory-count/` |
| Importer un fichier Excel / CSV | ✅ | ❌ | `POST /api/articles/import/` |
| **Enregistrer une vente** | ✅ | ✅ | `POST /api/sales/` |
| Accorder une remise | ✅ sans limite | ✅ jusqu'à `CASHIER_MAX_DISCOUNT_PERCENT` % (20 % par défaut), motif obligatoire | `POST /api/sales/` |
| Consulter les ventes | ✅ toutes | ✅ **les siennes** (ou toutes si `CASHIERS_SEE_ALL_SALES=True`) | `GET /api/sales/` |
| Annuler une vente | ✅ (motif obligatoire) | ❌ | `POST /api/sales/{id}/cancel/` |
| Consulter les statistiques financières | ✅ | ✅ (sans marges ni coûts) | `GET /api/dashboard/summary/` |
| Consulter / exporter les rapports | ✅ | ✅ lecture seule | `GET /api/reports/...` |
| Faire un compte rendu de caisse | ✅ | ✅ (le sien) | `POST /api/cash-reports/` |
| Valider un compte rendu de caisse | ✅ | ❌ | `POST /api/cash-reports/{id}/review/` |
| Gérer les comptes utilisateurs | ✅ | ❌ | `/api/users/` |
| Consulter le journal d'audit | ✅ | ❌ | `GET /api/audit-logs/` |
| Ses notifications | ✅ | ✅ (uniquement les siennes) | `/api/notifications/` |

## Utiliser les droits dans le frontend

`GET /api/auth/me/` (et la réponse de connexion) contient un objet `capabilities` :

```json
{
  "view_catalog": true, "view_stock": true, "create_sale": true, "view_sales": true,
  "view_all_sales": false, "view_dashboard": true, "view_reports": true, "export_reports": true,
  "submit_cash_report": true, "view_purchase_prices": false, "manage_catalog": false,
  "manage_stock": false, "import_files": false, "cancel_sale": false, "manage_users": false,
  "view_audit_log": false
}
```

Affichez les menus et boutons en fonction de ces valeurs plutôt que de tester
le rôle : si une règle change côté serveur, le frontend suit automatiquement.

## Où c'est codé

- `apps/common/permissions.py` : `IsAdmin`, `IsAdminOrReadOnly`.
- `apps/accounts/models.py` : `User.capabilities`.
- Chaque `views.py` déclare `permission_classes` ou `get_permissions()`.
- Les champs réservés à l'admin sont retirés par `AdminOnlyFieldsMixin` (`apps/catalog/serializers.py`).
- Les tests `tests/test_permissions.py` vérifient cette matrice.
