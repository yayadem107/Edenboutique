from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.common.exceptions import BusinessError
from apps.common.exports import csv_response, wants_csv
from apps.common.permissions import IsAdmin, is_admin
from apps.notifications.models import Notification
from apps.notifications.services import notify_admins

from .filters import CashReportFilter, SaleFilter
from .models import CashReport, Sale
from .serializers import (
    CashReportReviewSerializer,
    CashReportSerializer,
    CashSummarySerializer,
    SaleCancelSerializer,
    SaleCreateSerializer,
    SaleListSerializer,
    SaleSerializer,
)
from .services import cancel_sale, compute_cash_summary, create_sale

SALE_EXPORT_COLUMNS = [
    ("number", "Numéro"), ("created_at", "Date"), ("cashier_name", "Caissier"), ("status_label", "Statut"),
    ("payment_method_label", "Paiement"), ("items_count", "Articles"), ("subtotal", "Sous-total"),
    ("discount_total", "Remises"), ("total", "Total"), ("customer_name", "Client"),
    ("cancellation_reason", "Motif d'annulation"),
]


@extend_schema_view(
    list=extend_schema(
        summary="Liste des ventes",
        description="Un caissier ne voit que ses propres ventes (sauf réglage CASHIERS_SEE_ALL_SALES).",
        parameters=[OpenApiParameter("export", str, enum=["csv"], description="`csv` pour télécharger")],
    ),
    retrieve=extend_schema(summary="Détail d'une vente (ticket)"),
)
@extend_schema(tags=["Ventes"])
class SaleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  viewsets.GenericViewSet):
    """Une vente ne se modifie pas et ne se supprime pas : elle s'annule (administrateur)."""

    filterset_class = SaleFilter
    search_fields = ["number", "customer_name", "customer_phone", "payment_reference", "lines__sku",
                     "lines__article_name"]
    ordering_fields = ["created_at", "total"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Sale.objects.none()
        queryset = Sale.objects.select_related("cashier", "cancelled_by").prefetch_related("lines")
        user = self.request.user
        if not is_admin(user) and not settings.BOUTIQUE["CASHIERS_SEE_ALL_SALES"]:
            queryset = queryset.filter(cashier=user)
        if self.request.query_params.get("search"):
            queryset = queryset.distinct()
        return queryset

    def get_serializer_class(self):
        return SaleListSerializer if self.action == "list" else SaleSerializer

    def get_permissions(self):
        if self.action == "cancel":
            return [IsAdmin()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        if wants_csv(request):
            rows = SaleListSerializer(self.filter_queryset(self.get_queryset())[:10000], many=True,
                                      context=self.get_serializer_context()).data
            return csv_response("ventes", SALE_EXPORT_COLUMNS, rows)
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Enregistrer une vente",
        description=(
            "Les prix sont calculés par le serveur. Le stock est décrémenté dans la même transaction ; "
            "si un seul article manque, rien n'est enregistré. Réponse 201 pour une nouvelle vente, "
            "200 si ce `client_request_id` a déjà été traité (pas de doublon)."
        ),
        request=SaleCreateSerializer,
        responses={201: SaleSerializer, 200: SaleSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        sale, created = create_sale(
            cashier=request.user, lines=data.pop("lines"), payment_method=data.pop("payment_method"),
            client_request_id=data.pop("client_request_id", None), request=request, **data,
        )
        if sale.cashier_id != request.user.pk:
            raise BusinessError({"client_request_id": "Cet identifiant de requête a déjà été utilisé."})
        sale = self.get_queryset().get(pk=sale.pk)
        return Response(SaleSerializer(sale, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(summary="Annuler une vente (administrateur) — remet les articles en stock",
                   request=SaleCancelSerializer, responses=SaleSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = SaleCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = cancel_sale(self.get_object(), user=request.user, reason=serializer.validated_data["reason"],
                           request=request)
        return Response(SaleSerializer(self.get_queryset().get(pk=sale.pk),
                                       context=self.get_serializer_context()).data)


@extend_schema_view(
    list=extend_schema(summary="Comptes rendus de caisse (les siens pour un caissier, tous pour l'admin)"),
    retrieve=extend_schema(summary="Détail d'un compte rendu"),
    create=extend_schema(
        summary="Envoyer le compte rendu de caisse de la journée",
        description="Le caissier saisit l'argent compté et un commentaire ; les totaux sont calculés par le serveur.",
    ),
    update=extend_schema(summary="Corriger son compte rendu (tant qu'il n'est pas vérifié)"),
    partial_update=extend_schema(summary="Corriger son compte rendu (tant qu'il n'est pas vérifié)"),
)
@extend_schema(tags=["Comptes rendus de caisse"])
class CashReportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = CashReportSerializer
    filterset_class = CashReportFilter
    ordering_fields = ["report_date", "created_at", "cash_difference"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CashReport.objects.none()
        queryset = CashReport.objects.select_related("cashier", "reviewed_by")
        if not is_admin(self.request.user):
            queryset = queryset.filter(cashier=self.request.user)
        return queryset

    def get_permissions(self):
        if self.action == "review":
            return [IsAdmin()]
        return super().get_permissions()

    def _fill_figures(self, serializer, cashier, day):
        summary = compute_cash_summary(cashier, day)
        counted = serializer.validated_data.get("counted_cash", getattr(serializer.instance, "counted_cash", 0))
        return serializer.save(cashier=cashier, **summary, cash_difference=counted - summary["expected_cash"])

    def perform_create(self, serializer):
        day = serializer.validated_data.get("report_date") or timezone.localdate()
        if CashReport.objects.filter(cashier=self.request.user, report_date=day).exists():
            raise BusinessError({"report_date": "Un compte rendu existe déjà pour cette journée : modifiez-le."})
        report = self._fill_figures(serializer, self.request.user, day)
        log_action(AuditLog.Action.CASH_REPORT, request=self.request, target=report,
                   details={"ecart": str(report.cash_difference)})
        level = Notification.Level.WARNING if report.cash_difference else Notification.Level.INFO
        notify_admins(
            Notification.Type.CASH_REPORT, "Compte rendu de caisse",
            f"{report.cashier} a envoyé son compte rendu du {report.report_date:%d/%m/%Y} : "
            f"{report.sales_count} vente(s), {report.total_sales} {settings.BOUTIQUE['CURRENCY']}, "
            f"écart de caisse {report.cash_difference}.",
            level=level, data={"cash_report_id": report.pk}, exclude=self.request.user,
        )

    def perform_update(self, serializer):
        report = serializer.instance
        if report.cashier_id != self.request.user.pk:
            raise BusinessError({"detail": "Seul l'auteur du compte rendu peut le corriger."})
        if report.status == CashReport.Status.REVIEWED:
            raise BusinessError({"detail": "Ce compte rendu a déjà été vérifié par l'administrateur."})
        day = serializer.validated_data.get("report_date", report.report_date)
        if day != report.report_date:
            raise BusinessError({"report_date": "La journée d'un compte rendu ne peut pas être changée."})
        report = self._fill_figures(serializer, report.cashier, day)
        log_action(AuditLog.Action.CASH_REPORT, request=self.request, target=report,
                   details={"correction": True, "ecart": str(report.cash_difference)})

    @extend_schema(
        summary="Aperçu des chiffres de la journée avant d'envoyer le compte rendu",
        parameters=[OpenApiParameter("date", str, description="AAAA-MM-JJ (aujourd'hui par défaut)")],
        responses=CashSummarySerializer,
    )
    @action(detail=False)
    def preview(self, request):
        day = parse_date(request.query_params.get("date", "")) or timezone.localdate()
        return Response(CashSummarySerializer(compute_cash_summary(request.user, day)).data)

    @extend_schema(summary="Valider un compte rendu (administrateur)", request=CashReportReviewSerializer,
                   responses={200: CashReportSerializer, 400: OpenApiResponse(description="Déjà vérifié")})
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        report = self.get_object()
        serializer = CashReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report.status = CashReport.Status.REVIEWED
        report.reviewed_by, report.reviewed_at = request.user, timezone.now()
        report.admin_comment = serializer.validated_data["admin_comment"]
        report.save()
        log_action(AuditLog.Action.UPDATE, request=request, target=report, details={"statut": "REVIEWED"})
        return Response(self.get_serializer(report).data)
