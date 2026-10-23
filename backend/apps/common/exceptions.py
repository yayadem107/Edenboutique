from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class BusinessError(serializers.ValidationError):
    """Règle métier non respectée (stock insuffisant, remise trop élevée…). Réponse 400."""


def custom_exception_handler(exc, context):
    """
    Convertit les erreurs Django en réponses JSON lisibles par le frontend :
    - ValidationError Django  -> 400 {"champ": ["message"]} ou {"detail": "..."}
    - ProtectedError (suppression d'un objet encore utilisé) -> 409
    """
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            exc = serializers.ValidationError(exc.message_dict)
        else:
            exc = serializers.ValidationError({"detail": exc.messages})
    elif isinstance(exc, ProtectedError):
        return Response(
            {
                "detail": (
                    "Impossible de supprimer cet élément car il est utilisé ailleurs "
                    "(ventes, mouvements, articles…). Archivez-le plutôt."
                )
            },
            status=status.HTTP_409_CONFLICT,
        )
    return exception_handler(exc, context)
