from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Category, Product, ProductVariant, Supplier
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    ProductVariantSerializer,
    SupplierSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    search_fields = ["name"]


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    search_fields = ["name", "phone", "email"]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = (
        Product.objects.select_related("category", "supplier")
        .prefetch_related("variants")
        .annotate(total_quantity=Coalesce(Sum("variants__quantity"), 0))
    )
    serializer_class = ProductSerializer
    filterset_fields = ["category", "supplier", "gender", "is_active", "brand"]
    search_fields = ["name", "reference", "brand"]
    ordering_fields = ["name", "sale_price", "created_at", "total_quantity"]


class ProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.select_related("product")
    serializer_class = ProductVariantSerializer
    filterset_fields = ["product", "size", "color", "product__category"]
    search_fields = ["sku", "barcode", "product__name", "color"]
    ordering_fields = ["quantity", "size"]

    @action(detail=False, url_path="low-stock")
    def low_stock(self, request):
        """Variantes dont le stock est inférieur ou égal au seuil d'alerte."""
        qs = self.filter_queryset(self.get_queryset()).filter(quantity__lte=F("alert_threshold"))
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
