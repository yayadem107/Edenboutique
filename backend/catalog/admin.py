from django.contrib import admin

from .models import Category, Product, ProductVariant, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent"]
    search_fields = ["name"]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "email"]
    search_fields = ["name"]


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    readonly_fields = ["quantity"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["reference", "name", "category", "brand", "sale_price", "is_active"]
    list_filter = ["category", "gender", "is_active"]
    search_fields = ["name", "reference", "brand"]
    inlines = [ProductVariantInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "size", "color", "quantity", "alert_threshold"]
    list_filter = ["product__category", "size"]
    search_fields = ["sku", "barcode", "product__name"]
    readonly_fields = ["quantity"]
