from django.contrib import admin

from .models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """Consultation seule : les mouvements se saisissent via l'API (qui applique les règles)."""

    list_display = ["created_at", "variant", "movement_type", "delta", "quantity_after", "user", "sale"]
    list_filter = ["movement_type", "created_at"]
    search_fields = ["variant__sku", "variant__article__name", "reason", "lot_number"]
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
