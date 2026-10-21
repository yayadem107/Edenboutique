from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F

from catalog.models import ProductVariant


class StockMovement(models.Model):
    """
    Journal des entrées/sorties de stock. La quantité d'une variante n'est
    jamais modifiée directement : elle évolue uniquement via ces mouvements.
    """

    class Type(models.TextChoices):
        IN = "IN", "Entrée (réception)"
        OUT = "OUT", "Sortie (vente)"
        RETURN = "RETURN", "Retour client"
        ADJUST = "ADJUST", "Ajustement d'inventaire"
        LOSS = "LOSS", "Perte / casse"

    # Sens appliqué à la quantité pour chaque type (ADJUST : quantity peut être signée).
    SIGN = {Type.IN: 1, Type.RETURN: 1, Type.OUT: -1, Type.LOSS: -1, Type.ADJUST: 1}

    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField("type", max_length=10, choices=Type.choices)
    quantity = models.IntegerField(
        "quantité", help_text="Positive, sauf pour un ajustement (peut être négative)."
    )
    unit_price = models.DecimalField(
        "prix unitaire", max_digits=10, decimal_places=2, null=True, blank=True
    )
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mouvement de stock"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} × {self.variant}"

    @property
    def delta(self):
        return self.SIGN[self.movement_type] * self.quantity

    def clean(self):
        if self.quantity == 0:
            raise ValidationError({"quantity": "La quantité ne peut pas être nulle."})
        if self.movement_type != self.Type.ADJUST and self.quantity < 0:
            raise ValidationError({"quantity": "La quantité doit être positive."})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Un mouvement de stock ne peut pas être modifié.")
        self.clean()
        with transaction.atomic():
            # Verrou de la ligne pour éviter les ventes simultanées en négatif.
            variant = ProductVariant.objects.select_for_update().get(pk=self.variant_id)
            if variant.quantity + self.delta < 0:
                raise ValidationError(
                    {"quantity": f"Stock insuffisant : {variant.quantity} disponible(s)."}
                )
            super().save(*args, **kwargs)
            ProductVariant.objects.filter(pk=variant.pk).update(quantity=F("quantity") + self.delta)
