import django_filters
from django.db.models import F, Q

from .models import Article, ArticleType, ArticleVariant, Gender

STOCK_STATUS_CHOICES = [("OUT", "Rupture"), ("LOW", "Stock faible"), ("OK", "Disponible"),
                        ("AVAILABLE", "En stock (faible ou non)")]


def filter_by_category(queryset, prefix, category_id):
    """Une catégorie principale inclut aussi les articles de ses sous-catégories."""
    return queryset.filter(Q(**{f"{prefix}category": category_id}) | Q(**{f"{prefix}category__parent": category_id}))


class ArticleFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(method="filter_category")
    article_type = django_filters.MultipleChoiceFilter(choices=ArticleType.choices)
    gender = django_filters.MultipleChoiceFilter(choices=Gender.choices)
    age_range = django_filters.NumberFilter(field_name="age_ranges", distinct=True)
    age_months = django_filters.NumberFilter(
        method="filter_age_months", help_text="Articles adaptés à un enfant de N mois (ex. 30 = 2 ans et demi)."
    )
    brand = django_filters.CharFilter(lookup_expr="icontains")
    min_price = django_filters.NumberFilter(field_name="sale_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="sale_price", lookup_expr="lte")
    stock_status = django_filters.ChoiceFilter(choices=STOCK_STATUS_CHOICES, method="filter_stock_status")

    class Meta:
        model = Article
        fields = ["supplier", "is_regulated", "is_archived"]

    def filter_category(self, queryset, name, value):
        return filter_by_category(queryset, "", value)

    def filter_age_months(self, queryset, name, value):
        return queryset.filter(age_ranges__min_months__lte=value, age_ranges__max_months__gte=value).distinct()

    def filter_stock_status(self, queryset, name, value):
        if value == "OUT":
            return queryset.filter(total_quantity__lte=0)
        if value == "AVAILABLE":
            return queryset.filter(total_quantity__gt=0)
        low = Q(variants__quantity__lte=F("variants__alert_threshold"), variants__is_active=True)
        if value == "LOW":
            return queryset.filter(low, total_quantity__gt=0).distinct()
        return queryset.filter(total_quantity__gt=0).exclude(low)


class ArticleVariantFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(method="filter_category")
    article_type = django_filters.MultipleChoiceFilter(field_name="article__article_type", choices=ArticleType.choices)
    gender = django_filters.MultipleChoiceFilter(field_name="article__gender", choices=Gender.choices)
    stock_status = django_filters.ChoiceFilter(choices=STOCK_STATUS_CHOICES, method="filter_stock_status")
    include_archived = django_filters.BooleanFilter(method="filter_noop",
                                                    help_text="Inclure les variantes d'articles archivés.")

    class Meta:
        model = ArticleVariant
        fields = ["article", "size", "color", "is_active", "barcode", "sku"]

    def filter_category(self, queryset, name, value):
        return filter_by_category(queryset, "article__", value)

    def filter_stock_status(self, queryset, name, value):
        if value == "OUT":
            return queryset.filter(quantity__lte=0)
        if value == "LOW":
            return queryset.filter(quantity__gt=0, quantity__lte=F("alert_threshold"))
        if value == "AVAILABLE":
            return queryset.filter(quantity__gt=0)
        return queryset.filter(quantity__gt=F("alert_threshold"))

    def filter_noop(self, queryset, name, value):
        return queryset
