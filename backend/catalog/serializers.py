from rest_framework import serializers

from .models import Category, Product, ProductVariant, Supplier


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "parent"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "email", "address"]


class ProductVariantSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id", "product", "product_name", "size", "color", "sku", "barcode",
            "quantity", "alert_threshold", "is_low_stock",
        ]
        read_only_fields = ["quantity"]


class ProductSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    total_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "reference", "category", "supplier", "brand", "gender",
            "description", "image", "purchase_price", "sale_price", "is_active",
            "total_quantity", "variants", "created_at", "updated_at",
        ]
