"""
Permissions par rôle. Elles sont TOUJOURS vérifiées côté serveur : le frontend
peut masquer des boutons, mais c'est ici que l'accès est réellement autorisé.
Voir docs/PERMISSIONS.md.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_active and user.is_admin)


class IsAdmin(BasePermission):
    """Réservé au super administrateur."""

    message = "Cette action est réservée à l'administrateur."

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrReadOnly(BasePermission):
    """Lecture pour tout utilisateur connecté, écriture pour l'administrateur."""

    message = "Seul l'administrateur peut modifier ces données."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or is_admin(request.user)
