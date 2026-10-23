from django.conf import settings
from django.db import models

from apps.catalog.models import ArticleVariant


class StockMovement(models.Model):
    """
    Journal de TOUTES les entrées et sorties de stock.

    La quantité d'une variante n'est jamais modifiée à la main : elle évolue
    uniquement via apps.inventory.services.apply_movement(), qui crée une
    ligne ici. Un mouvement ne peut ni être modifié ni supprimé ; une erreur
    se corrige par un mouvement inverse.
    """

    class Type(models.TextChoices):
        PURCHASE = "PURCHASE", "Entrée – réception fournisseur"
        CUSTOMER_RETURN = "CUSTOMER_RETURN", "Entrée – retour client"
        ADJUST_IN = "ADJUST_IN", "Entrée – ajustement d'inventaire"
        SALE = "SALE", "Sortie – vente"
        SALE_CANCEL = "SALE_CANCEL", "Entrée – annulation de vente"
        ADJUST_OUT = "ADJUST_OUT", "Sortie – ajustement d'inventaire"
        LOSS = "LOSS", "Sortie – perte, casse ou vol"
        SUPPLIER_RETURN = "SUPPLIER_RETURN", "Sortie – retour fournisseur"

    INCOMING = {Type.PURCHASE, Type.CUSTOMER_RETURN, Type.ADJUST_IN, Type.SALE_CANCEL}
    # Types que l'administrateur peut saisir à la main (les autres viennent des ventes).
    MANUAL = {
        Type.PURCHASE, Type.CUSTOMER_RETURN, Type.ADJUST_IN,
        Type.ADJUST_OUT, Type.LOSS, Type.SUPPLIER_RETURN,
    }

    variant = models.ForeignKey(
        ArticleVariant, on_delete=models.PROTECT, related_name="movements", verbose_name="variante"
    )
    movement_type = models.CharField("type", max_length=20, choices=Type.choices, db_index=True)
    quantity = models.PositiveIntegerField("quantité")
    delta = models.IntegerField("variation", help_text="+ pour une entrée, – pour une sortie")
    quantity_before = models.IntegerField("stock avant")
    quantity_after = models.IntegerField("stock après")
    reason = models.CharField("motif / justification", max_length=255, blank=True)
    lot_number = models.CharField("numéro de lot", max_length=64, blank=True, db_index=True)
    unit_cost = models.DecimalField("coût unitaire", max_digits=12, decimal_places=2, null=True, blank=True)
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.PROTECT, null=True, blank=True,
        related_name="stock_movements", verbose_name="vente",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements",
        verbose_name="effectué par",
    )
    created_at = models.DateTimeField("date", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "mouvement de stock"
        verbose_name_plural = "mouvements de stock"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="movement_quantity_positive"),
            models.CheckConstraint(condition=models.Q(quantity_after__gte=0), name="movement_stock_not_negative"),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} : {self.delta:+d} × {self.variant}"

    @property
    def is_incoming(self):
        return self.movement_type in self.INCOMING

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Un mouvement de stock ne peut pas être modifié.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Un mouvement de stock ne peut pas être supprimé.")
