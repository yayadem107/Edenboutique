from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import StockMovement


class StockMovementSerializer(serializers.ModelSerializer):
    variant_label = serializers.CharField(source="variant.__str__", read_only=True)
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "variant", "variant_label", "movement_type", "quantity",
            "unit_price", "note", "user", "created_at",
        ]

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
