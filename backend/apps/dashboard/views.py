from django.conf import settings
from django.db.models import F
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ArticleVariant
from apps.common.exports import csv_response, wants_csv
from apps.common.permissions import is_admin
from apps.notifications.models import Notification
from apps.sales.serializers import SaleListSerializer

from . import services

PERIOD_PARAMS = [
    OpenApiParameter("period", str, enum=list(services.PERIODS),
                     description="Période (par défaut : today). `custom` exige date_from."),
    OpenApiParameter("date_from", OpenApiTypes.DATE, description="Début (AAAA-MM-JJ)"),
    OpenApiParameter("date_to", OpenApiTypes.DATE, description="Fin incluse (AAAA-MM-JJ)"),
]
EXPORT_PARAM = OpenApiParameter("export", str, enum=["csv"], description="`csv` pour télécharger le rapport")
FILTER_PARAMS = [
    OpenApiParameter("cashier", int, description="Filtrer sur un caissier (admin)"),
    OpenApiParameter("payment_method", str, description="CASH, MOBILE_MONEY, CARD…"),
]


def period_payload(start, end, label):
    return {"start": start, "end": end, "label": label}


class ReportView(APIView):
    """Base des rapports : lecture seule pour tout utilisateur connecté."""

    def sales_for(self, request, start, end):
        """
        Les chiffres globaux sont visibles par tous. En revanche, un caissier qui
        filtre par caissier ne peut obtenir que ses propres chiffres.
        """
        params = request.query_params
        restricted = not is_admin(request.user) and not settings.BOUTIQUE["CASHIERS_SEE_ALL_SALES"]
        cashier = request.user if restricted and params.get("cashier") else None
        return services.filtered_sales(start, end, params, cashier=cashier)


@extend_schema(tags=["Tableau de bord"])
class DashboardSummaryView(ReportView):
    @extend_schema(summary="Indicateurs du tableau de bord", parameters=PERIOD_PARAMS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        admin = is_admin(request.user)
        start, end, label = services.resolve_period(request.query_params)
        sales = services.filtered_sales(start, end)
        my_sales = sales.filter(cashier=request.user)
        recent = (my_sales if not admin and not settings.BOUTIQUE["CASHIERS_SEE_ALL_SALES"] else sales)
        recent = recent.select_related("cashier").prefetch_related("lines")[:5]
        alerts = (ArticleVariant.objects.select_related("article", "size", "color")
                  .filter(is_active=True, article__is_archived=False, quantity__lte=F("alert_threshold"))
                  .order_by("quantity")[:10])
        return Response({
            "period": period_payload(start, end, label),
            "currency": settings.BOUTIQUE["CURRENCY"],
            "sales": services.sales_figures(sales, include_margin=admin),
            "my_sales": services.sales_figures(my_sales),
            "by_payment_method": services.by_payment_method(sales),
            "top_articles": services.top_articles(sales, limit=5),
            "stock": services.stock_figures(include_cost=admin),
            "stock_alerts": [
                {"variant_id": v.pk, "label": str(v), "sku": v.sku, "quantity": v.quantity,
                 "alert_threshold": v.alert_threshold, "stock_status": v.stock_status}
                for v in alerts
            ],
            "recent_sales": SaleListSerializer(recent, many=True, context={"request": request}).data,
            "unread_notifications": Notification.objects.filter(recipient=request.user, is_read=False).count(),
        })


@extend_schema(tags=["Rapports"])
class SalesReportView(ReportView):
    @extend_schema(
        summary="Rapport des ventes (chiffre d'affaires par jour ou par mois)",
        parameters=[*PERIOD_PARAMS, *FILTER_PARAMS, EXPORT_PARAM,
                    OpenApiParameter("group_by", str, enum=["day", "month"])],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        start, end, label = services.resolve_period(request.query_params)
        sales = self.sales_for(request, start, end)
        group_by = "month" if request.query_params.get("group_by") == "month" else "day"
        series = services.sales_timeseries(sales, group_by)
        if wants_csv(request):
            return csv_response("rapport-ventes", [
                ("period", "Période"), ("sales_count", "Ventes"), ("items_sold", "Articles vendus"),
                ("revenue", "Chiffre d'affaires"), ("discounts", "Remises")], series)
        return Response({
            "period": period_payload(start, end, label),
            "totals": services.sales_figures(sales, include_margin=is_admin(request.user)),
            "by_payment_method": services.by_payment_method(sales),
            "series": series,
        })


@extend_schema(tags=["Rapports"])
class TopArticlesReportView(ReportView):
    @extend_schema(
        summary="Articles les plus vendus",
        parameters=[*PERIOD_PARAMS, *FILTER_PARAMS, EXPORT_PARAM,
                    OpenApiParameter("limit", int, description="Nombre d'articles (défaut 10, max 100)"),
                    OpenApiParameter("category", int, description="Catégorie (inclut les sous-catégories)")],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        start, end, label = services.resolve_period(request.query_params)
        try:
            limit = max(1, min(int(request.query_params.get("limit", 10)), 100))
        except ValueError:
            limit = 10
        rows = services.top_articles(self.sales_for(request, start, end), limit=limit,
                                     category=request.query_params.get("category"),
                                     include_margin=is_admin(request.user))
        if wants_csv(request):
            return csv_response("articles-plus-vendus", [
                ("reference", "Référence"), ("name", "Article"), ("category", "Catégorie"),
                ("quantity_sold", "Quantité vendue"), ("sales_count", "Nombre de ventes"),
                ("revenue", "Chiffre d'affaires")], rows)
        return Response({"period": period_payload(start, end, label), "results": rows})


@extend_schema(tags=["Rapports"])
class StockReportView(ReportView):
    @extend_schema(
        summary="État du stock : quantités, ruptures, valeur du stock",
        description="L'export CSV contient une ligne par variante. La valeur au prix d'achat est réservée à l'admin.",
        parameters=[EXPORT_PARAM, OpenApiParameter("category", int),
                    OpenApiParameter("stock_status", str, enum=["OUT", "LOW", "OK"])],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        admin = is_admin(request.user)
        category = request.query_params.get("category")
        if wants_csv(request):
            return self._export(request, admin, category)
        return Response({
            "totals": services.stock_figures(include_cost=admin, category=category),
            "by_category": services.stock_by_category(include_cost=admin),
        })

    def _export(self, request, admin, category):
        from apps.catalog.filters import ArticleVariantFilter

        queryset = ArticleVariant.objects.select_related("article__category", "size", "color").filter(
            article__is_archived=False)
        queryset = ArticleVariantFilter(request.query_params, queryset=queryset).qs
        rows = [{
            "sku": v.sku, "barcode": v.barcode or "", "reference": v.article.reference, "article": v.article.name,
            "category": str(v.article.category), "size": v.size.label if v.size else "",
            "color": v.color.name if v.color else "", "quantity": v.quantity, "alert_threshold": v.alert_threshold,
            "status": {"OUT": "Rupture", "LOW": "Stock faible", "OK": "Disponible"}[v.stock_status],
            "sale_price": v.effective_price, "stock_value_sale": v.effective_price * v.quantity,
            "purchase_price": v.article.purchase_price, "stock_value_cost": v.article.purchase_price * v.quantity,
        } for v in queryset.order_by("article__name", "sku")]
        columns = [("sku", "SKU"), ("barcode", "Code-barres"), ("reference", "Référence"), ("article", "Article"),
                   ("category", "Catégorie"), ("size", "Taille"), ("color", "Couleur"), ("quantity", "Quantité"),
                   ("alert_threshold", "Seuil"), ("status", "État"), ("sale_price", "Prix de vente"),
                   ("stock_value_sale", "Valeur (prix de vente)")]
        if admin:
            columns += [("purchase_price", "Prix d'achat"), ("stock_value_cost", "Valeur (prix d'achat)")]
        return csv_response("etat-du-stock", columns, rows)


@extend_schema(tags=["Rapports"])
class CashierReportView(ReportView):
    @extend_schema(
        summary="Ventes par caissier",
        description="Un caissier ne voit que sa propre ligne (sauf réglage CASHIERS_SEE_ALL_SALES).",
        parameters=[*PERIOD_PARAMS, EXPORT_PARAM], responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        start, end, label = services.resolve_period(request.query_params)
        sales = services.filtered_sales(start, end)
        if not is_admin(request.user) and not settings.BOUTIQUE["CASHIERS_SEE_ALL_SALES"]:
            sales = sales.filter(cashier=request.user)
        rows = services.cashier_figures(sales)
        if wants_csv(request):
            return csv_response("ventes-par-caissier", [
                ("cashier_name", "Caissier"), ("sales_count", "Ventes"), ("revenue", "Chiffre d'affaires"),
                ("discounts", "Remises"), ("cancelled_count", "Ventes annulées")], rows)
        return Response({"period": period_payload(start, end, label), "results": rows})
