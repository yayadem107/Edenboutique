#!/bin/sh
# Prépare la base avant de démarrer le serveur : migrations + données de référence.
set -e

python manage.py migrate --noinput
python manage.py init_boutique

if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.production" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
