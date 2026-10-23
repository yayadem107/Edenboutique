import uuid

from django.conf import settings
from django.db import models

from apps.catalog.models import ArticleVariant


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Espèces"
    MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"
    CARD = "CARD", "Carte bancaire"
    BANK_TRANSFER = "BANK_TRANSFER", "Virement"
    OTHER = "OTHER", "Autre"


class Sale(models.Model):
    """
    Vente effectuée en boutique. Les prix sont TOUJOURS calculés par le serveur
    à partir du catalogue : le frontend n'envoie que les articles, quantités et remises.
    """

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Validée"
        CANCELLED = "CANCELLED", "Annulée"

    number = models.CharField("numéro", max_length=30, unique=True, null=True, blank=True,
                              help_text="ex. V20261023-00042, attribué automatiquement.")
    client_request_id = models.UUIDField(
        "identifiant de requête", unique=True, default=uuid.uuid4,
        help_text="UUID généré par le frontend : renvoyer la même vente deux fois ne la duplique pas.",
    )
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name="sales", verbose_name="caissier")
    status = models.CharField("statut", max_length=10, choices=Status.choices,
                              default=Status.COMPLETED, db_index=True)
    payment_method = models.CharField("moyen de paiement", max_length=20, choices=PaymentMethod.choices)
    payment_reference = models.CharField("référence de paiement", max_length=100, blank=True,
                                         help_text="ex. numéro de transaction Mobile Money")
    subtotal = models.DecimalField("sous-total", max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField("total des remises", max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField("total à payer", max_digits=12, decimal_places=2, default=0)
    amount_received = models.DecimalField("montant reçu", max_digits=12, decimal_places=2, null=True, blank=True)
    change_due = models.DecimalField("monnaie rendue", max_digits=12, decimal_places=2, default=0)
    customer_name = models.CharField("nom du client", max_length=150, blank=True)
    customer_phone = models.CharField("téléphone du client", max_length=30, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField("date", auto_now_add=True, db_index=True)

    cancelled_at = models.DateTimeField("annulée le", null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True,
                                     blank=True, related_name="+", verbose_name="annulée par")
    cancellation_reason = models.CharField("motif d'annulation", max_length=255, blank=True)

    class Meta:
        verbose_name = "vente"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gte=0), name="sale_total_positive"),
        ]

    def __str__(self):
        return self.number or f"Vente #{self.pk}"

    @property
    def items_count(self):
        return sum(line.quantity for line in self.lines.all())


class SaleLine(models.Model):
    """Ligne de vente. Nom, SKU et prix sont copiés : l'historique reste exact si le catalogue change."""

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines", verbose_name="vente")
    variant = models.ForeignKey(ArticleVariant, on_delete=models.PROTECT, related_name="sale_lines",
                                verbose_name="variante")
    article_name = models.CharField("article", max_length=150)
    variant_label = models.CharField("variante", max_length=200)
    sku = models.CharField(max_length=64)
    quantity = models.PositiveIntegerField("quantité")
    unit_price = models.DecimalField("prix unitaire", max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField("coût unitaire", max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField("remise", max_digits=12, decimal_places=2, default=0)
    discount_reason = models.CharField("motif de la remise", max_length=255, blank=True)
    line_total = models.DecimalField("total de la ligne", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "ligne de vente"
        verbose_name_plural = "lignes de vente"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="sale_line_quantity_positive"),
            models.CheckConstraint(condition=models.Q(discount_amount__gte=0), name="sale_line_discount_positive"),
            models.CheckConstraint(condition=models.Q(line_total__gte=0), name="sale_line_total_positive"),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.variant_label}"


class CashReport(models.Model):
    """
    Compte rendu de caisse de fin de journée rédigé par un caissier.
    Les montants attendus sont calculés par le serveur ; le caissier saisit
    l'argent réellement compté et un commentaire. L'administrateur le valide.
    """

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Envoyé"
        REVIEWED = "REVIEWED", "Vérifié par l'administrateur"

    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name="cash_reports", verbose_name="caissier")
    report_date = models.DateField("journée")
    sales_count = models.PositiveIntegerField("nombre de ventes", default=0)
    cancelled_count = models.PositiveIntegerField("ventes annulées", default=0)
    items_sold = models.PositiveIntegerField("articles vendus", default=0)
    total_sales = models.DecimalField("chiffre d'affaires", max_digits=12, decimal_places=2, default=0)
    total_discounts = models.DecimalField("remises accordées", max_digits=12, decimal_places=2, default=0)
    totals_by_payment = models.JSONField("totaux par moyen de paiement", default=dict)
    expected_cash = models.DecimalField("espèces attendues", max_digits=12, decimal_places=2, default=0)
    counted_cash = models.DecimalField("espèces comptées", max_digits=12, decimal_places=2)
    cash_difference = models.DecimalField("écart de caisse", max_digits=12, decimal_places=2, default=0)
    comment = models.TextField("commentaire du caissier", blank=True)
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.SUBMITTED)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True,
                                    blank=True, related_name="+", verbose_name="vérifié par")
    reviewed_at = models.DateTimeField("vérifié le", null=True, blank=True)
    admin_comment = models.TextField("commentaire de l'administrateur", blank=True)
    created_at = models.DateTimeField("envoyé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        verbose_name = "compte rendu de caisse"
        verbose_name_plural = "comptes rendus de caisse"
        ordering = ["-report_date", "cashier__full_name"]
        constraints = [
            models.UniqueConstraint(fields=["cashier", "report_date"], name="one_cash_report_per_day"),
        ]

    def __str__(self):
        return f"Compte rendu {self.report_date:%d/%m/%Y} – {self.cashier}"
