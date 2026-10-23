"""Réglages des tests automatisés (utilisés automatiquement par `python manage.py test`)."""

from .development import *  # noqa: F401,F403

# Hachage rapide : les tests créent beaucoup de comptes. Jamais en production !
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
