import django_filters

from .models import CashReport, Sale


class SaleFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    min_total = django_filters.NumberFilter(field_name="total", lookup_expr="gte")
    max_total = django_filters.NumberFilter(field_name="total", lookup_expr="lte")
    has_discount = django_filters.BooleanFilter(method="filter_has_discount")
    variant = django_filters.NumberFilter(field_name="lines__variant", distinct=True)
    article = django_filters.NumberFilter(field_name="lines__variant__article", distinct=True)

    class Meta:
        model = Sale
        fields = ["status", "cashier", "payment_method", "number"]

    def filter_has_discount(self, queryset, name, value):
        return queryset.filter(discount_total__gt=0) if value else queryset.filter(discount_total=0)


class CashReportFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="report_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="report_date", lookup_expr="lte")

    class Meta:
        model = CashReport
        fields = ["cashier", "status", "report_date"]
