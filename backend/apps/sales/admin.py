from django.contrib import admin

from .models import CashReport, Sale, SaleLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SaleLine._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """Consultation seule : ventes et annulations passent par l'API pour garder le stock cohérent."""

    list_display = ["number", "created_at", "cashier", "payment_method", "total", "discount_total", "status"]
    list_filter = ["status", "payment_method", "cashier", "created_at"]
    search_fields = ["number", "customer_name", "customer_phone"]
    readonly_fields = [f.name for f in Sale._meta.fields]
    inlines = [SaleLineInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CashReport)
class CashReportAdmin(admin.ModelAdmin):
    list_display = ["report_date", "cashier", "sales_count", "total_sales", "expected_cash",
                    "counted_cash", "cash_difference", "status"]
    list_filter = ["status", "cashier", "report_date"]
    readonly_fields = [f.name for f in CashReport._meta.fields if f.name not in ("admin_comment",)]

    def has_add_permission(self, request):
        return False
