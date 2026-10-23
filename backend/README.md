# Eden Boutique – Backend

API REST de gestion de stock d'une boutique de vêtements et d'articles pour enfants (0–15 ans) :
articles, stock, ventes, utilisateurs, alertes, rapports et chiffre d'affaires.

**Stack** : Python 3.12 · Django 5.2 · Django REST Framework · PostgreSQL 16+ · JWT · Swagger · Docker Compose

| Document | Pour qui / quoi |
|---|---|
| [docs/API.md](docs/API.md) | **Guide du frontend** : authentification, endpoints, exemples, erreurs |
| [docs/PERMISSIONS.md](docs/PERMISSIONS.md) | Qui a le droit de faire quoi (admin / caissier) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Organisation du code, modèle de données, garanties |
| <http://localhost:8000/api/docs/> | Documentation interactive Swagger (une fois le serveur lancé) |

---

## Démarrage rapide avec Docker (recommandé)

Prérequis : [Docker Desktop](https://www.docker.com/products/docker-desktop/) et Git.

```bash
git clone https://github.com/yayadem107/Edenboutique.git
cd Edenboutique/backend
cp .env.example .env          # Windows PowerShell : copy .env.example .env
```

Ouvrir `.env` et remplacer au minimum `SECRET_KEY` et `POSTGRES_PASSWORD`
(générer une clé : `python -c "import secrets; print(secrets.token_urlsafe(50))"`).

```bash
docker compose up --build
```

Au premier démarrage, le conteneur crée les tables et charge les catégories, tranches d'âge,
tailles et couleurs. Dans un **second terminal** :

```bash
# Créer le super administrateur (identifiant, nom complet, mot de passe)
docker compose exec api python manage.py createsuperuser

# Facultatif : comptes, articles et ventes de démonstration pour développer le frontend
docker compose exec api python manage.py seed_demo --password "ChoisirUnMotDePasse"
```

C'est prêt :

- API : <http://localhost:8000/api/>
- Swagger : <http://localhost:8000/api/docs/>
- Administration Django : <http://localhost:8000/admin/>

Arrêter : `Ctrl+C` puis `docker compose down` (les données sont conservées dans un volume ;
`docker compose down -v` efface aussi la base).

---

## Installation sans Docker

Prérequis : Python 3.12+ et PostgreSQL 16+ installés.

**1. Créer la base PostgreSQL** (avec `psql` ou pgAdmin) :

```sql
CREATE USER eden WITH PASSWORD 'mot-de-passe-a-choisir';
CREATE DATABASE edenboutique OWNER eden;
```

**2. Installer le projet** :

```bash
cd Edenboutique/backend
python -m venv .venv
# Windows : .venv\Scripts\activate      macOS / Linux : source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Dans `.env`, mettre une `SECRET_KEY` et adapter
`DATABASE_URL=postgres://eden:mot-de-passe-a-choisir@localhost:5432/edenboutique`.

**3. Initialiser et lancer** :

```bash
python manage.py migrate
python manage.py init_boutique          # catégories, âges, tailles, couleurs
python manage.py createsuperuser        # le super administrateur
python manage.py seed_demo --password "ChoisirUnMotDePasse"   # facultatif
python manage.py runserver
```

---

## Les comptes

- **Super administrateur** : `python manage.py createsuperuser`.
- **Caissiers (3 au maximum)** : l'administrateur les crée depuis le frontend (`POST /api/users/`)
  ou depuis `/admin/`. Chaque caissier a son nom complet et son propre mot de passe, qu'il doit
  changer à sa première connexion.
- Aucune inscription publique n'existe.
- `seed_demo` crée `admin`, `caissier1`, `caissier2`, `caissier3` avec le mot de passe passé en
  paramètre — **uniquement pour le développement** (refusé si `DEBUG=False`).

## Commandes utiles

| Commande | Rôle |
|---|---|
| `python manage.py test` | Lancer les 98 tests automatisés (nécessite PostgreSQL) |
| `python manage.py init_boutique` | (Re)charger les données de référence, sans doublon |
| `python manage.py seed_demo --password X` | Données de démonstration |
| `python manage.py makemigrations` / `migrate` | Après une modification de `models.py` |
| `python manage.py spectacular --file docs/openapi.yaml` | Régénérer le schéma OpenAPI |

Avec Docker, préfixer par `docker compose exec api` (ex. `docker compose exec api python manage.py test`).

## Connecter le frontend PWA

1. Mettre l'adresse du frontend dans `CORS_ALLOWED_ORIGINS` (et `CSRF_TRUSTED_ORIGINS`) du `.env`,
   par ex. `http://localhost:5173` pour Vite.
2. Se connecter avec `POST /api/auth/login/`, puis envoyer `Authorization: Bearer <access>`.
3. Lire [docs/API.md](docs/API.md) : renouvellement des tokens, vente sans doublon
   (`client_request_id`), scanner de code-barres, exports CSV, conseils hors ligne.

## Mise en production (résumé)

- `DJANGO_SETTINGS_MODULE=config.settings.production`, `DEBUG=False`, vraie `SECRET_KEY`,
  `ALLOWED_HOSTS` et `CORS_ALLOWED_ORIGINS` avec le domaine réel, HTTPS obligatoire.
- L'image Docker démarre avec `gunicorn` ; l'entrypoint exécute les migrations et `collectstatic`.
- Les fichiers statiques sont servis par WhiteNoise ; les photos des articles (`media/`) doivent
  être servies par le serveur web (Nginx, Caddy…) ou un stockage objet.
- Sauvegarder régulièrement PostgreSQL (`pg_dump`) et le dossier `media/` (photos des articles).
- Ne jamais lancer `seed_demo` en production.
