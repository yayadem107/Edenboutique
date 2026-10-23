from rest_framework import serializers

from apps.catalog.models import ArticleVariant

from .models import StockMovement


class StockMovementSerializer(serializers.ModelSerializer):
    """Lecture d'un mouvement (historique)."""

    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    variant_label = serializers.CharField(source="variant.__str__", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    article_id = serializers.IntegerField(source="variant.article_id", read_only=True)
    user_name = serializers.CharField(source="user.__str__", read_only=True)
    sale_number = serializers.CharField(source="sale.number", read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = [
            "id", "variant", "variant_label", "sku", "article_id", "movement_type",
            "movement_type_label", "quantity", "delta", "quantity_before", "quantity_after",
            "reason", "lot_number", "unit_cost", "sale", "sale_number", "user", "user_name",
            "created_at",
        ]
        read_only_fields = fields


def validate_manual_movement(attrs):
    """Règles communes à toute saisie manuelle de mouvement."""
    movement_type = attrs["movement_type"]
    variant = attrs["variant"]
    if movement_type != StockMovement.Type.PURCHASE and not attrs.get("reason", "").strip():
        raise serializers.ValidationError({"reason": "Un motif est obligatoire pour ce type de mouvement."})
    if (movement_type == StockMovement.Type.PURCHASE and variant.article.is_regulated
            and not attrs.get("lot_number", "").strip()):
        raise serializers.ValidationError(
            {"lot_number": f"Numéro de lot obligatoire : « {variant.article.name} » est un produit réglementé."}
        )
    return attrs


class StockMovementCreateSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=ArticleVariant.objects.select_related("article"))
    movement_type = serializers.ChoiceField(
        choices=[(t.value, t.label) for t in StockMovement.Type if t in StockMovement.MANUAL],
        help_text="Les ventes et annulations génèrent leurs mouvements automatiquement.",
    )
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    lot_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)

    def validate(self, attrs):
        return validate_manual_movement(attrs)


class ReceptionLineSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=ArticleVariant.objects.select_related("article"))
    quantity = serializers.IntegerField(min_value=1)
    lot_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)


class ReceptionSerializer(serializers.Serializer):
    """Réception d'une livraison complète en une seule fois."""

    reason = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default="",
        help_text="ex. « Livraison fournisseur X, bon n°123 »",
    )
    lines = ReceptionLineSerializer(many=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("Ajoutez au moins une ligne.")
        for line in lines:
            validate_manual_movement({**line, "movement_type": StockMovement.Type.PURCHASE})
        return lines


class InventoryCountSerializer(serializers.Serializer):
    """Comptage physique : le serveur calcule et enregistre l'écart."""

    variant = serializers.PrimaryKeyRelatedField(queryset=ArticleVariant.objects.all())
    counted_quantity = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=255, default="Inventaire physique")
