from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Alerte affichée dans l'application (cloche de notifications du frontend)."""

    class Type(models.TextChoices):
        SALE = "SALE", "Nouvelle vente"
        SALE_CANCELLED = "SALE_CANCELLED", "Vente annulée"
        LOW_STOCK = "LOW_STOCK", "Stock faible"
        OUT_OF_STOCK = "OUT_OF_STOCK", "Rupture de stock"
        CASH_REPORT = "CASH_REPORT", "Compte rendu de caisse"
        SENSITIVE_ACTION = "SENSITIVE_ACTION", "Action sensible"

    class Level(models.TextChoices):
        INFO = "info", "Information"
        WARNING = "warning", "Attention"
        DANGER = "danger", "Urgent"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="destinataire",
    )
    type = models.CharField(max_length=30, choices=Type.choices, db_index=True)
    level = models.CharField("niveau", max_length=10, choices=Level.choices, default=Level.INFO)
    title = models.CharField("titre", max_length=150)
    message = models.TextField()
    # Informations pour que le frontend ouvre le bon écran, ex. {"sale_id": 12}
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField("lue", default=False, db_index=True)
    read_at = models.DateTimeField("lue le", null=True, blank=True)
    created_at = models.DateTimeField("date", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} → {self.recipient}"
