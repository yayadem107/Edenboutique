from .models import AuditLog


def get_client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(action, *, user=None, request=None, target=None, details=None, username=""):
    """
    Enregistre une action dans le journal d'audit.

    Exemple : log_action(AuditLog.Action.ARCHIVE, request=request, target=article)
    """
    if user is None and request is not None and request.user.is_authenticated:
        user = request.user
    return AuditLog.objects.create(
        user=user,
        username=username or (user.get_username() if user else ""),
        action=action,
        target_type=target._meta.label if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        target_repr=str(target)[:255] if target is not None else "",
        details=details or {},
        ip_address=get_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
    )


class AuditedViewSetMixin:
    """
    À ajouter aux ViewSets d'administration : chaque création, modification
    et suppression est automatiquement inscrite au journal d'audit.
    """

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(AuditLog.Action.CREATE, request=self.request, target=instance,
                   details={"donnees": _json_safe(serializer.validated_data)})

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(AuditLog.Action.UPDATE, request=self.request, target=instance,
                   details={"modifications": _json_safe(serializer.validated_data)})

    def perform_destroy(self, instance):
        log_action(AuditLog.Action.DELETE, request=self.request, target=instance)
        instance.delete()


def _json_safe(data):
    """Convertit les valeurs (objets, décimaux, fichiers…) en texte pour le stockage JSON."""
    safe = {}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple)) or hasattr(value, "all"):
            safe[key] = [str(v) for v in value]
        else:
            safe[key] = str(value)
    return safe
