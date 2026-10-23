Le backend de l'appli de gestion de stock Eden Boutique est prêt. C'est une API Django REST Framework avec PostgreSQL, et ton travail sera de faire le frontend PWA.

📦 Dépôt : https://github.com/yayadem107/Edenboutique (tout le backend est dans le dossier backend/)

🛠️ Prérequis

Git
Python 3.12 ou plus récent
PostgreSQL 16 ou plus récent (installé en local), ou bien Docker Desktop (il s'occupe de PostgreSQL pour toi)
Node.js 20+ pour le frontend, avec le framework de ton choix (React/Vite, Vue, Angular…)
🚀 Installation sans Docker

Dans PostgreSQL, crée l'utilisateur et la base : CREATE USER eden WITH PASSWORD 'ton-mot-de-passe'; CREATE DATABASE edenboutique OWNER eden;
Dans un terminal :

git clone https://github.com/yayadem107/Edenboutique.git
cd Edenboutique/backend
python -m venv .venv
.venv\Scripts\activate          (Mac/Linux : source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          (Mac/Linux : cp)
Dans .env : mets une SECRET_KEY au hasard, ton mot de passe dans DATABASE_URL, et l'adresse de ton frontend dans CORS_ALLOWED_ORIGINS (par exemple http://localhost:5173).
Puis :

python manage.py migrate
python manage.py init_boutique
python manage.py seed_demo --password "UnMotDePasseDeTest"
python manage.py runserver
seed_demo crée des comptes de test (admin, caissier1, caissier2, caissier3, tous avec le mot de passe que tu choisis), des articles et quelques ventes, pour que tu aies des données à afficher.
🐳 Avec Docker : docker compose up --build dans backend/ (les détails sont dans le README). Attention, cette partie n'a pas encore pu être testée de mon côté. Si ça coince, utilise l'installation sans Docker.

📚 À lire, dans cet ordre

backend/README.md : l'installation
backend/docs/API.md : le guide du frontend (connexion, tous les endpoints, exemples JSON, erreurs, exports, conseils PWA)
backend/docs/PERMISSIONS.md : ce que l'admin et les caissiers ont le droit de faire
La doc interactive Swagger sur http://localhost:8000/api/docs/ une fois le serveur lancé. Tu peux aussi générer les types TypeScript : npx openapi-typescript http://localhost:8000/api/schema/ -o src/api/schema.d.ts
🔑 Les points importants pour le frontend

Connexion : POST /api/auth/login/ renvoie des tokens et le profil. Ensuite, envoie Authorization: Bearer <access> à chaque requête. Le token dure 30 minutes. Quand tu reçois une erreur 401, appelle /api/auth/refresh/.
Menus : affiche-les selon user.capabilities, plutôt qu'en testant le rôle. Si must_change_password vaut true, affiche l'écran de changement de mot de passe.
Ventes : n'envoie jamais de prix, le serveur les calcule. Génère un client_request_id (crypto.randomUUID()) par panier : si la requête est renvoyée, la vente n'est pas comptée deux fois, même hors ligne.
Scanner de code-barres : GET /api/variants/lookup/?code=...
Notifications : interroge GET /api/notifications/unread-count/ toutes les 30 à 60 secondes.
Messages : les libellés (*_label) et les messages d'erreur sont déjà en français, tu peux les afficher tels quels.
Tests du backend : python manage.py test (98 tests).
⚠️ Si l'installation de PostgreSQL échoue avec initdb: failed to restore old locale (ça arrive avec un Windows réglé sur « Français (Côte d'Ivoire) ») : initialise avec initdb --locale=C -E UTF8.

N'hésite pas si tu as des questions !