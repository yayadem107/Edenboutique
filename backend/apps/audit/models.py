from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Trace qui a fait quoi et quand. Une entrée ne peut être ni modifiée ni supprimée."""

    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Connexion"
        LOGIN_FAILED = "LOGIN_FAILED", "Échec de connexion"
        LOGOUT = "LOGOUT", "Déconnexion"
        PASSWORD_CHANGED = "PASSWORD_CHANGED", "Mot de passe modifié"
        PASSWORD_RESET = "PASSWORD_RESET", "Mot de passe réinitialisé par l'admin"
        CREATE = "CREATE", "Création"
        UPDATE = "UPDATE", "Modification"
        DELETE = "DELETE", "Suppression"
        ARCHIVE = "ARCHIVE", "Archivage"
        RESTORE = "RESTORE", "Restauration"
        STOCK_MOVEMENT = "STOCK_MOVEMENT", "Mouvement de stock"
        STOCK_IMPORT = "STOCK_IMPORT", "Import de fichier"
        SALE_CREATED = "SALE_CREATED", "Vente enregistrée"
        SALE_CANCELLED = "SALE_CANCELLED", "Vente annulée"
        CASH_REPORT = "CASH_REPORT", "Compte rendu de caisse"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="utilisateur",
    )
    username = models.CharField(
        "identifiant", max_length=150, blank=True, help_text="Conservé même si le compte change."
    )
    action = models.CharField(max_length=30, choices=Action.choices, db_index=True)
    target_type = models.CharField("type d'objet", max_length=60, blank=True, db_index=True)
    target_id = models.CharField("id de l'objet", max_length=40, blank=True)
    target_repr = models.CharField("objet", max_length=255, blank=True)
    details = models.JSONField("détails", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("adresse IP", null=True, blank=True)
    user_agent = models.CharField("navigateur", max_length=255, blank=True)
    created_at = models.DateTimeField("date", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "entrée du journal d'audit"
        verbose_name_plural = "journal d'audit"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%d/%m/%Y %H:%M} – {self.username} – {self.get_action_display()}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Le journal d'audit est en lecture seule.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Le journal d'audit est en lecture seule.")
