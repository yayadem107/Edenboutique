"""Calculs des indicateurs. Tous les montants sont calculés en base de données (PostgreSQL)."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncMonth
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.catalog.models import Article, ArticleVariant
from apps.common.exceptions import BusinessError
from apps.sales.models import Sale, SaleLine

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=14, decimal_places=2)

PERIODS = {
    "today": "Aujourd'hui", "yesterday": "Hier", "week": "7 derniers jours",
    "month": "Mois en cours", "last_month": "Mois dernier", "year": "Année en cours", "custom": "Personnalisée",
}


def resolve_period(params):
    """Traduit ?period=…&date_from=…&date_to=… en (date début, date fin, libellé)."""
    period = params.get("period") or ("custom" if params.get("date_from") else "today")
    today = timezone.localdate()
    if period == "today":
        start = end = today
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
    elif period == "week":
        start, end = today - timedelta(days=6), today
    elif period == "month":
        start, end = today.replace(day=1), today
    elif period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif period == "year":
        start, end = today.replace(month=1, day=1), today
    elif period == "custom":
        start = parse_date(params.get("date_from", "") or "")
        end = parse_date(params.get("date_to", "") or "") or today
        if start is None:
            raise BusinessError({"date_from": "Date de début obligatoire (AAAA-MM-JJ) pour une période personnalisée."})
        if start > end:
            raise BusinessError({"date_from": "La date de début doit précéder la date de fin."})
    else:
        raise BusinessError({"period": f"Période inconnue. Valeurs possibles : {', '.join(PERIODS)}."})
    return start, end, PERIODS[period]


def filtered_sales(start, end, params=None, cashier=None):
    params = params or {}
    sales = Sale.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    if cashier is not None:
        sales = sales.filter(cashier=cashier)
    elif params.get("cashier"):
        sales = sales.filter(cashier=params["cashier"])
    if params.get("payment_method"):
        sales = sales.filter(payment_method=params["payment_method"])
    return sales


def line_margin():
    return ExpressionWrapper(F("line_total") - F("unit_cost") * F("quantity"), output_field=MONEY)


def sales_figures(sales, include_margin=False):
    completed = sales.filter(status=Sale.Status.COMPLETED)
    totals = completed.aggregate(
        revenue=Coalesce(Sum("total"), ZERO, output_field=MONEY),
        discounts=Coalesce(Sum("discount_total"), ZERO, output_field=MONEY),
        count=Count("id"),
    )
    lines = SaleLine.objects.filter(sale__in=completed)
    line_totals = lines.aggregate(items=Coalesce(Sum("quantity"), 0),
                                  margin=Coalesce(Sum(line_margin()), ZERO, output_field=MONEY))
    cancelled = sales.filter(status=Sale.Status.CANCELLED).aggregate(
        count=Count("id"), amount=Coalesce(Sum("total"), ZERO, output_field=MONEY))
    figures = {
        "revenue": totals["revenue"],
        "sales_count": totals["count"],
        "items_sold": line_totals["items"],
        "average_basket": (totals["revenue"] / totals["count"]).quantize(Decimal("0.01")) if totals["count"] else ZERO,
        "discounts_total": totals["discounts"],
        "cancelled_count": cancelled["count"],
        "cancelled_amount": cancelled["amount"],
    }
    if include_margin:
        figures["gross_margin"] = line_totals["margin"]
    return figures


def by_payment_method(sales):
    return [
        {"payment_method": row["payment_method"], "label": Sale(payment_method=row["payment_method"])
         .get_payment_method_display(), "sales_count": row["count"], "amount": row["amount"]}
        for row in sales.filter(status=Sale.Status.COMPLETED).values("payment_method")
        .annotate(count=Count("id"), amount=Sum("total")).order_by("-amount")
    ]


def sales_timeseries(sales, group_by="day"):
    trunc = TruncMonth if group_by == "month" else TruncDay
    completed = sales.filter(status=Sale.Status.COMPLETED)
    rows = (completed.annotate(bucket=trunc("created_at")).values("bucket")
            .annotate(sales_count=Count("id"), revenue=Sum("total"), discounts=Sum("discount_total"))
            .order_by("bucket"))
    items = dict(
        SaleLine.objects.filter(sale__in=completed).annotate(bucket=trunc("sale__created_at"))
        .values("bucket").annotate(n=Sum("quantity")).values_list("bucket", "n")
    )
    fmt = "%Y-%m" if group_by == "month" else "%Y-%m-%d"
    return [{"period": row["bucket"].strftime(fmt), "sales_count": row["sales_count"], "revenue": row["revenue"],
             "discounts": row["discounts"], "items_sold": items.get(row["bucket"], 0)} for row in rows]


def top_articles(sales, limit=10, category=None, include_margin=False):
    lines = SaleLine.objects.filter(sale__in=sales.filter(status=Sale.Status.COMPLETED))
    if category:
        lines = lines.filter(Q(variant__article__category=category) | Q(variant__article__category__parent=category))
    annotations = {"quantity_sold": Sum("quantity"), "revenue": Sum("line_total"), "sales_count": Count("sale", distinct=True)}
    if include_margin:
        annotations["gross_margin"] = Sum(line_margin())
    rows = (lines.values("variant__article", "variant__article__reference", "variant__article__name",
                         "variant__article__category__name")
            .annotate(**annotations).order_by("-quantity_sold", "-revenue")[:limit])
    return [{
        "article_id": r.pop("variant__article"), "reference": r.pop("variant__article__reference"),
        "name": r.pop("variant__article__name"), "category": r.pop("variant__article__category__name"), **r,
    } for r in rows]


def stock_figures(include_cost=False, category=None):
    variants = ArticleVariant.objects.filter(article__is_archived=False, is_active=True)
    if category:
        variants = variants.filter(Q(article__category=category) | Q(article__category__parent=category))
    sale_price = Coalesce(F("price_override"), F("article__sale_price"))
    totals = variants.aggregate(
        variants_count=Count("id"),
        units_in_stock=Coalesce(Sum("quantity"), 0),
        out_of_stock_count=Count("id", filter=Q(quantity__lte=0)),
        low_stock_count=Count("id", filter=Q(quantity__gt=0, quantity__lte=F("alert_threshold"))),
        stock_value_sale=Coalesce(Sum(ExpressionWrapper(F("quantity") * sale_price, output_field=MONEY)),
                                  ZERO, output_field=MONEY),
        stock_value_cost=Coalesce(Sum(ExpressionWrapper(F("quantity") * F("article__purchase_price"),
                                                        output_field=MONEY)), ZERO, output_field=MONEY),
    )
    articles = Article.objects.filter(is_archived=False)
    if category:
        articles = articles.filter(Q(category=category) | Q(category__parent=category))
    totals["articles_count"] = articles.count()
    if not include_cost:
        totals.pop("stock_value_cost")
    return totals


def stock_by_category(include_cost=False):
    variants = ArticleVariant.objects.filter(article__is_archived=False, is_active=True)
    root = Coalesce(F("article__category__parent__name"), F("article__category__name"))
    sale_price = Coalesce(F("price_override"), F("article__sale_price"))
    annotations = {
        "units_in_stock": Sum("quantity"),
        "variants_count": Count("id"),
        "out_of_stock_count": Count("id", filter=Q(quantity__lte=0)),
        "stock_value_sale": Sum(ExpressionWrapper(F("quantity") * sale_price, output_field=MONEY)),
    }
    if include_cost:
        annotations["stock_value_cost"] = Sum(ExpressionWrapper(F("quantity") * F("article__purchase_price"),
                                                                output_field=MONEY))
    return list(variants.annotate(category=root).values("category").annotate(**annotations).order_by("category"))


def cashier_figures(sales):
    rows = (sales.values("cashier", "cashier__full_name", "cashier__username")
            .annotate(sales_count=Count("id", filter=Q(status=Sale.Status.COMPLETED)),
                      revenue=Coalesce(Sum("total", filter=Q(status=Sale.Status.COMPLETED)), ZERO, output_field=MONEY),
                      discounts=Coalesce(Sum("discount_total", filter=Q(status=Sale.Status.COMPLETED)), ZERO,
                                         output_field=MONEY),
                      cancelled_count=Count("id", filter=Q(status=Sale.Status.CANCELLED)))
            .order_by("-revenue"))
    return [{"cashier_id": r["cashier"], "cashier_name": r["cashier__full_name"] or r["cashier__username"],
             "sales_count": r["sales_count"], "revenue": r["revenue"], "discounts": r["discounts"],
             "cancelled_count": r["cancelled_count"]} for r in rows]
