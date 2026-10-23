from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from apps.common.permissions import IsAdmin

from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


@extend_schema_view(
    list=extend_schema(summary="Journal d'audit (admin)"),
    retrieve=extend_schema(summary="Détail d'une entrée du journal"),
)
@extend_schema(tags=["Audit"])
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("user")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filterset_class = AuditLogFilter
    search_fields = ["username", "target_repr", "target_type"]
    ordering_fields = ["created_at", "action"]
