import django_filters

from .models import StockMovement


class StockMovementFilter(django_filters.FilterSet):
    article = django_filters.NumberFilter(field_name="variant__article")
    category = django_filters.NumberFilter(method="filter_category")
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    direction = django_filters.ChoiceFilter(
        choices=[("in", "Entrées"), ("out", "Sorties")], method="filter_direction"
    )

    class Meta:
        model = StockMovement
        fields = ["variant", "movement_type", "user", "sale", "lot_number"]

    def filter_category(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(Q(variant__article__category=value) | Q(variant__article__category__parent=value))

    def filter_direction(self, queryset, name, value):
        return queryset.filter(delta__gt=0) if value == "in" else queryset.filter(delta__lt=0)
