from django.contrib import admin

from .models import AgeRange, Article, ArticleVariant, Category, Color, Size, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "default_article_type", "sort_order", "is_active"]
    list_filter = ["parent", "is_active"]
    search_fields = ["name"]
    readonly_fields = ["slug"]


@admin.register(AgeRange)
class AgeRangeAdmin(admin.ModelAdmin):
    list_display = ["label", "min_months", "max_months", "sort_order", "is_active"]


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ["label", "system", "sort_order"]
    list_filter = ["system"]


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ["name", "hex_code"]
    search_fields = ["name"]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "contact_name", "phone", "email", "is_active"]
    search_fields = ["name"]


class ArticleVariantInline(admin.TabularInline):
    model = ArticleVariant
    extra = 0
    readonly_fields = ["quantity"]
    fields = ["size", "color", "sku", "barcode", "price_override", "quantity", "alert_threshold", "is_active"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["reference", "name", "category", "article_type", "gender", "sale_price", "is_archived"]
    list_filter = ["article_type", "gender", "category", "is_regulated", "is_archived"]
    search_fields = ["name", "reference", "brand"]
    filter_horizontal = ["age_ranges"]
    inlines = [ArticleVariantInline]


@admin.register(ArticleVariant)
class ArticleVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "article", "size", "color", "quantity", "alert_threshold", "is_active"]
    list_filter = ["article__category", "size", "color"]
    search_fields = ["sku", "barcode", "article__name"]
    readonly_fields = ["quantity"]
