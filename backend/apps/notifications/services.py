from django.contrib.auth import get_user_model

from .models import Notification


def notify_admins(type, title, message, *, level=Notification.Level.INFO, data=None, exclude=None):
    """Envoie une notification à chaque administrateur actif (sauf `exclude`)."""
    User = get_user_model()
    admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
    if exclude is not None:
        admins = admins.exclude(pk=exclude.pk)
    return Notification.objects.bulk_create(
        Notification(
            recipient=admin, type=type, level=level, title=title, message=message, data=data or {}
        )
        for admin in admins
    )
