from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.permissions import is_admin

from .models import AgeRange, Article, ArticleVariant, Category, Color, Size, Supplier


class AdminOnlyFieldsMixin:
    """Retire de la réponse les champs listés dans `admin_only_fields` pour les caissiers."""

    admin_only_fields = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not is_admin(request.user):
            for field in self.admin_only_fields:
                data.pop(field, None)
        return data


def run_model_clean(instance):
    try:
        instance.clean()
    except DjangoValidationError as exc:
        raise serializers.ValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        ) from exc


# --- Référentiels --------------------------------------------------------------

class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    article_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "parent_name", "default_article_type",
                  "description", "sort_order", "is_active", "article_count"]
        read_only_fields = ["slug"]

    def validate(self, attrs):
        current = self.instance
        run_model_clean(Category(
            pk=current.pk if current else None,
            name=attrs.get("name", current.name if current else ""),
            parent=attrs.get("parent", current.parent if current else None),
        ))
        return attrs


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "default_article_type", "sort_order", "is_active", "children"]


class AgeRangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgeRange
        fields = ["id", "label", "min_months", "max_months", "sort_order", "is_active"]

    def validate(self, attrs):
        current = {f: getattr(self.instance, f) for f in ("min_months", "max_months")} if self.instance else {}
        run_model_clean(AgeRange(**{**current, **attrs}))
        return attrs


class SizeSerializer(serializers.ModelSerializer):
    system_label = serializers.CharField(source="get_system_display", read_only=True)

    class Meta:
        model = Size
        fields = ["id", "label", "system", "system_label", "sort_order"]


class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ["id", "name", "hex_code"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_name", "phone", "email", "address", "notes",
                  "is_active", "created_at", "updated_at"]


# --- Variantes -----------------------------------------------------------------

class ArticleVariantSerializer(serializers.ModelSerializer):
    article_name = serializers.CharField(source="article.name", read_only=True)
    article_reference = serializers.CharField(source="article.reference", read_only=True)
    size_label = serializers.CharField(source="size.label", read_only=True, default=None)
    color_name = serializers.CharField(source="color.name", read_only=True, default=None)
    effective_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    stock_status = serializers.CharField(read_only=True)
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = ArticleVariant
        fields = [
            "id", "article", "article_name", "article_reference", "label", "size", "size_label",
            "color", "color_name", "sku", "barcode", "price_override", "effective_price",
            "quantity", "alert_threshold", "stock_status", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["quantity"]
        extra_kwargs = {"sku": {"required": False}, "price_override": {"min_value": 0}}

    def validate(self, attrs):
        if self.instance and "article" in attrs and attrs["article"] != self.instance.article:
            raise serializers.ValidationError({"article": "Une variante ne peut pas changer d'article."})
        merged = {
            "article": attrs.get("article", getattr(self.instance, "article", None)),
            "size": attrs.get("size", getattr(self.instance, "size", None)),
            "color": attrs.get("color", getattr(self.instance, "color", None)),
        }
        run_model_clean(ArticleVariant(pk=getattr(self.instance, "pk", None), **merged))
        return attrs


class InitialVariantSerializer(serializers.Serializer):
    size = serializers.PrimaryKeyRelatedField(queryset=Size.objects.all(), allow_null=True, required=False)
    color = serializers.PrimaryKeyRelatedField(queryset=Color.objects.all(), allow_null=True, required=False)
    barcode = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    price_override = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    alert_threshold = serializers.IntegerField(min_value=0, required=False, default=2)
    initial_quantity = serializers.IntegerField(min_value=0, required=False, default=0)
    lot_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


# --- Articles ------------------------------------------------------------------

class ArticleSerializer(AdminOnlyFieldsMixin, serializers.ModelSerializer):
    admin_only_fields = ("purchase_price", "margin", "supplier", "supplier_name", "created_by")

    category_name = serializers.CharField(source="category.__str__", read_only=True)
    article_type_label = serializers.CharField(source="get_article_type_display", read_only=True)
    gender_label = serializers.CharField(source="get_gender_display", read_only=True)
    age_range_labels = serializers.SlugRelatedField(source="age_ranges", slug_field="label", many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    total_quantity = serializers.IntegerField(read_only=True, default=0)
    stock_status = serializers.SerializerMethodField()
    margin = serializers.SerializerMethodField()
    variants = ArticleVariantSerializer(many=True, read_only=True)
    initial_variants = InitialVariantSerializer(
        many=True, write_only=True, required=False,
        help_text="À la création uniquement : variantes à créer avec leur stock initial.",
    )

    class Meta:
        model = Article
        fields = [
            "id", "name", "reference", "category", "category_name", "article_type", "article_type_label",
            "gender", "gender_label", "age_ranges", "age_range_labels", "brand", "supplier", "supplier_name",
            "description", "material", "care_instructions", "image", "purchase_price", "sale_price", "margin",
            "is_regulated", "safety_standard", "safety_warnings", "min_age_months", "attributes",
            "is_archived", "archived_at", "total_quantity", "stock_status", "variants", "initial_variants",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["is_archived", "archived_at", "created_by"]
        extra_kwargs = {"purchase_price": {"min_value": 0}, "sale_price": {"min_value": 0}}

    @extend_schema_field(serializers.ChoiceField(choices=["OUT", "LOW", "OK"]))
    def get_stock_status(self, article):
        variants = list(article.variants.all())
        if not variants or all(v.quantity <= 0 for v in variants):
            return "OUT"
        if any(v.stock_status in ("LOW", "OUT") for v in variants if v.is_active):
            return "LOW"
        return "OK"

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_margin(self, article):
        return str(article.sale_price - article.purchase_price)

    def validate_category(self, category):
        if not category.is_active:
            raise serializers.ValidationError("Cette catégorie est désactivée.")
        return category

    def validate(self, attrs):
        if self.instance and "initial_variants" in attrs:
            raise serializers.ValidationError(
                {"initial_variants": "Utilisez /api/variants/ pour ajouter une variante à un article existant."}
            )
        fields = ("is_regulated", "safety_standard")
        current = {f: getattr(self.instance, f) for f in fields} if self.instance else {}
        run_model_clean(Article(**{**current, **{f: attrs[f] for f in fields if f in attrs}}))

        if attrs.get("is_regulated"):
            for variant in attrs.get("initial_variants", []):
                if variant.get("initial_quantity") and not variant.get("lot_number"):
                    raise serializers.ValidationError(
                        {"initial_variants": "Numéro de lot obligatoire pour le stock initial d'un produit réglementé."}
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from apps.inventory.models import StockMovement
        from apps.inventory.services import apply_movement

        initial_variants = validated_data.pop("initial_variants", [])
        user = self.context["request"].user
        article = super().create({**validated_data, "created_by": user})
        for data in initial_variants:
            quantity = data.pop("initial_quantity", 0)
            lot_number = data.pop("lot_number", "")
            variant = ArticleVariant(article=article, **data)
            run_model_clean(variant)
            variant.save()
            if quantity:
                apply_movement(variant, StockMovement.Type.PURCHASE, quantity, user,
                               reason="Stock initial à la création de l'article", lot_number=lot_number,
                               unit_cost=article.purchase_price)
        return article
