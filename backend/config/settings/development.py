"""Réglages de développement (machine locale ou Docker Compose)."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)

# En développement, on accepte aussi la session Django pour tester l'API
# directement depuis l'interface navigable de DRF après connexion à /admin/.
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [  # noqa: F405
    "rest_framework_simplejwt.authentication.JWTAuthentication",
    "rest_framework.authentication.SessionAuthentication",
]

if not CORS_ALLOWED_ORIGINS:  # noqa: F405
    # Ports par défaut de Vite, Create React App, Angular et Vue CLI.
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:4200",
        "http://localhost:8080",
    ]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
