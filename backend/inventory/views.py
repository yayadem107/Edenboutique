from rest_framework import mixins, viewsets

from .models import StockMovement
from .serializers import StockMovementSerializer


class StockMovementViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Les mouvements sont immuables : création et consultation uniquement."""

    queryset = StockMovement.objects.select_related("variant__product", "user")
    serializer_class = StockMovementSerializer
    filterset_fields = ["variant", "movement_type", "variant__product"]
    search_fields = ["note", "variant__sku", "variant__product__name"]
    ordering_fields = ["created_at", "quantity"]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
