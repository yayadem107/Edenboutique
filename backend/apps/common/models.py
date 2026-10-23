from django.db import models


class TimeStampedModel(models.Model):
    """Ajoute automatiquement les dates de création et de dernière modification."""

    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True
