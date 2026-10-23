from django.utils import timezone
from rest_framework import serializers

from apps.catalog.serializers import AdminOnlyFieldsMixin

from .models import CashReport, PaymentMethod, Sale, SaleLine


class SaleLineSerializer(AdminOnlyFieldsMixin, serializers.ModelSerializer):
    admin_only_fields = ("unit_cost",)

    class Meta:
        model = SaleLine
        fields = ["id", "variant", "article_name", "variant_label", "sku", "quantity", "unit_price",
                  "unit_cost", "discount_amount", "discount_reason", "line_total"]
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)
    cashier_name = serializers.CharField(source="cashier.__str__", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_label = serializers.CharField(source="get_payment_method_display", read_only=True)
    cancelled_by_name = serializers.CharField(source="cancelled_by.__str__", read_only=True, default=None)
    items_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "number", "client_request_id", "status", "status_label", "cashier", "cashier_name",
            "payment_method", "payment_method_label", "payment_reference", "subtotal", "discount_total",
            "total", "amount_received", "change_due", "customer_name", "customer_phone", "note",
            "items_count", "lines", "created_at", "cancelled_at", "cancelled_by", "cancelled_by_name",
            "cancellation_reason",
        ]
        read_only_fields = fields


class SaleListSerializer(SaleSerializer):
    """Version allégée pour les listes (sans le détail des lignes)."""

    class Meta(SaleSerializer.Meta):
        fields = [f for f in SaleSerializer.Meta.fields if f != "lines"]
        read_only_fields = fields


class SaleLineInputSerializer(serializers.Serializer):
    variant = serializers.IntegerField(help_text="id de la variante (taille × couleur) vendue")
    quantity = serializers.IntegerField(min_value=1, max_value=1000)
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, default=0,
        help_text="Remise en montant sur la ligne (pas en %).",
    )
    discount_reason = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default="",
        help_text="Obligatoire dès qu'une remise est accordée.",
    )


class SaleCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(
        required=False,
        help_text="UUID généré par le frontend au moment d'ouvrir le panier. Le renvoyer en cas de "
                  "nouvel essai : la vente ne sera jamais enregistrée deux fois.",
    )
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    payment_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    amount_received = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True,
        help_text="Montant donné par le client (espèces) : le serveur calcule la monnaie à rendre.",
    )
    customer_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    customer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    lines = SaleLineInputSerializer(many=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("La vente doit contenir au moins un article.")
        if len(lines) > 200:
            raise serializers.ValidationError("200 lignes maximum par vente.")
        return lines


class SaleCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, help_text="Motif obligatoire, conservé dans l'historique.")


# --- Comptes rendus de caisse ---------------------------------------------------

class CashReportSerializer(serializers.ModelSerializer):
    cashier_name = serializers.CharField(source="cashier.__str__", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.__str__", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CashReport
        fields = [
            "id", "cashier", "cashier_name", "report_date", "sales_count", "cancelled_count", "items_sold",
            "total_sales", "total_discounts", "totals_by_payment", "expected_cash", "counted_cash",
            "cash_difference", "comment", "status", "status_label", "reviewed_by", "reviewed_by_name",
            "reviewed_at", "admin_comment", "created_at", "updated_at",
        ]
        read_only_fields = [f for f in fields if f not in ("report_date", "counted_cash", "comment")]
        extra_kwargs = {"report_date": {"required": False}}

    def validate_report_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Impossible de faire le compte rendu d'une journée future.")
        return value


class CashReportReviewSerializer(serializers.Serializer):
    admin_comment = serializers.CharField(required=False, allow_blank=True, default="")


class CashSummarySerializer(serializers.Serializer):
    report_date = serializers.DateField()
    sales_count = serializers.IntegerField()
    cancelled_count = serializers.IntegerField()
    items_sold = serializers.IntegerField()
    total_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_discounts = serializers.DecimalField(max_digits=12, decimal_places=2)
    totals_by_payment = serializers.DictField(child=serializers.CharField())
    expected_cash = serializers.DecimalField(max_digits=12, decimal_places=2)
