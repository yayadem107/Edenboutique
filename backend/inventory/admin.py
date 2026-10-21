from django.contrib import admin

from .models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["created_at", "variant", "movement_type", "quantity", "user"]
    list_filter = ["movement_type", "created_at"]
    search_fields = ["variant__sku", "variant__product__name", "note"]
    autocomplete_fields = ["variant"]
    exclude = ["user"]

    def save_model(self, request, obj, form, change):
        obj.user = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        return False
