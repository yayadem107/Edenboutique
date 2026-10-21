# Eden Boutique – Backend

API Django REST de gestion de stock pour une boutique de vêtements.

## Stack

- Django 5.2, Django REST Framework, JWT (simplejwt)
- PostgreSQL (recommandé) ou MySQL, via `DATABASE_URL` — SQLite par défaut en développement
- Documentation OpenAPI / Swagger (drf-spectacular)

## Installation

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # puis éditer SECRET_KEY et DATABASE_URL
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### PostgreSQL

```sql
CREATE USER eden WITH PASSWORD 'motdepasse';
CREATE DATABASE edenboutique OWNER eden;
```

Puis dans `.env` : `DATABASE_URL=postgres://eden:motdepasse@localhost:5432/edenboutique`

Pour MySQL : `pip install mysqlclient` et `DATABASE_URL=mysql://eden:motdepasse@localhost:3306/edenboutique`.

## Modèle de données

| App | Modèle | Rôle |
|---|---|---|
| catalog | `Category` | Catégories (hiérarchiques) |
| catalog | `Supplier` | Fournisseurs |
| catalog | `Product` | Modèle de vêtement (référence, prix, marque, genre) |
| catalog | `ProductVariant` | Article stocké : taille + couleur, SKU, quantité, seuil d'alerte |
| inventory | `StockMovement` | Entrées, ventes, retours, pertes, ajustements |

La quantité d'une variante n'est **jamais** modifiée directement : chaque
mouvement de stock la met à jour de façon atomique et refuse un stock négatif.

## Endpoints

| URL | Description |
|---|---|
| `/admin/` | Administration Django |
| `/api/docs/` | Swagger UI |
| `/api/auth/token/`, `/api/auth/token/refresh/` | Authentification JWT |
| `/api/categories/`, `/api/suppliers/`, `/api/products/` | CRUD catalogue |
| `/api/variants/`, `/api/variants/low-stock/` | Variantes et alertes de stock bas |
| `/api/movements/` | Mouvements de stock (création + consultation) |

## Tests

```powershell
python manage.py test
```
