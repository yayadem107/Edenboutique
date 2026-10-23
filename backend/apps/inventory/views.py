from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.catalog.models import ArticleVariant
from apps.audit.services import log_action
from apps.common.exports import csv_response, wants_csv
from apps.common.permissions import IsAdmin

from .filters import StockMovementFilter
from .models import StockMovement
from .serializers import (
    InventoryCountSerializer,
    ReceptionSerializer,
    StockMovementCreateSerializer,
    StockMovementSerializer,
)
from .services import apply_movement

EXPORT_COLUMNS = [
    ("created_at", "Date"), ("movement_type_label", "Type"), ("sku", "SKU"),
    ("variant_label", "Article"), ("delta", "Variation"), ("quantity_before", "Stock avant"),
    ("quantity_after", "Stock après"), ("reason", "Motif"), ("lot_number", "Lot"),
    ("sale_number", "Vente"), ("user_name", "Utilisateur"),
]


@extend_schema_view(
    list=extend_schema(
        summary="Historique des mouvements de stock",
        parameters=[OpenApiParameter("export", str, enum=["csv"], description="`csv` pour télécharger")],
    ),
    retrieve=extend_schema(summary="Détail d'un mouvement"),
)
@extend_schema(tags=["Stock"])
class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture : tous les utilisateurs connectés.
    Saisie (entrée, sortie justifiée, inventaire) : administrateur uniquement.
    """

    queryset = StockMovement.objects.select_related("variant__article", "variant__size",
                                                    "variant__color", "user", "sale")
    serializer_class = StockMovementSerializer
    filterset_class = StockMovementFilter
    search_fields = ["variant__sku", "variant__barcode", "variant__article__name",
                     "variant__article__reference", "reason", "lot_number"]
    ordering_fields = ["created_at", "quantity", "delta"]

    def get_permissions(self):
        if self.action in ("create", "reception", "inventory_count"):
            return [IsAdmin()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        if wants_csv(request):
            rows = StockMovementSerializer(self.filter_queryset(self.get_queryset())[:10000], many=True).data
            return csv_response("mouvements-stock", EXPORT_COLUMNS, rows)
        return super().list(request, *args, **kwargs)

    def _log(self, movement):
        log_action(AuditLog.Action.STOCK_MOVEMENT, request=self.request, target=movement.variant,
                   details={"mouvement": movement.pk, "type": movement.movement_type,
                            "variation": movement.delta, "motif": movement.reason})

    @extend_schema(summary="Saisir un mouvement (entrée, sortie justifiée, perte…)",
                   request=StockMovementCreateSerializer, responses={201: StockMovementSerializer})
    def create(self, request):
        serializer = StockMovementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        movement = apply_movement(
            data["variant"], data["movement_type"], data["quantity"], request.user,
            reason=data["reason"], lot_number=data["lot_number"], unit_cost=data.get("unit_cost"),
        )
        self._log(movement)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary="Réceptionner une livraison (plusieurs articles d'un coup)",
                   request=ReceptionSerializer, responses={201: StockMovementSerializer(many=True)})
    @action(detail=False, methods=["post"])
    def reception(self, request):
        serializer = ReceptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]
        with transaction.atomic():
            movements = [
                apply_movement(line["variant"], StockMovement.Type.PURCHASE, line["quantity"], request.user,
                               reason=reason, lot_number=line["lot_number"], unit_cost=line.get("unit_cost"))
                for line in serializer.validated_data["lines"]
            ]
        for movement in movements:
            self._log(movement)
        return Response(StockMovementSerializer(movements, many=True).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Inventaire : saisir la quantité comptée en rayon",
        description="Le serveur crée l'ajustement correspondant à l'écart. Renvoie 200 sans mouvement si le stock est juste.",
        request=InventoryCountSerializer, responses={200: StockMovementSerializer, 201: StockMovementSerializer},
    )
    @action(detail=False, methods=["post"], url_path="inventory-count")
    def inventory_count(self, request):
        serializer = InventoryCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            variant = ArticleVariant.objects.select_for_update().get(pk=data["variant"].pk)
            difference = data["counted_quantity"] - variant.quantity
            if difference == 0:
                return Response({"detail": "Stock exact, aucun ajustement nécessaire.", "quantity": variant.quantity})
            movement_type = StockMovement.Type.ADJUST_IN if difference > 0 else StockMovement.Type.ADJUST_OUT
            movement = apply_movement(variant, movement_type, abs(difference), request.user, reason=data["reason"])
        self._log(movement)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
