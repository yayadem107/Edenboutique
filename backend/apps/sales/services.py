"""
Logique des ventes. Toute vente passe par create_sale(), toute annulation par
cancel_sale() : ce sont les seuls endroits où les règles sont appliquées.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.common.exceptions import BusinessError
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement, lock_variants
from apps.notifications.models import Notification
from apps.notifications.services import notify_admins

from .models import PaymentMethod, Sale, SaleLine

CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def create_sale(*, cashier, lines, payment_method, client_request_id=None, request=None, **extra):
    """
    Enregistre une vente et décrémente le stock, en une seule transaction.

    lines : [{"variant": id, "quantity": 2, "discount_amount": Decimal, "discount_reason": "..."}]
    Renvoie (vente, created). created=False si la même requête a déjà été traitée
    (double clic, réseau coupé puis renvoi par la PWA…).
    """
    if client_request_id:
        existing = Sale.objects.filter(client_request_id=client_request_id).first()
        if existing:
            return existing, False
    try:
        sale = _create_sale_atomic(cashier, lines, payment_method, client_request_id, extra)
    except IntegrityError:
        existing = Sale.objects.filter(client_request_id=client_request_id).first() if client_request_id else None
        if existing is None:
            raise
        return existing, False

    log_action(AuditLog.Action.SALE_CREATED, user=cashier, request=request, target=sale,
               details={"total": str(sale.total), "remises": str(sale.discount_total),
                        "paiement": sale.payment_method, "articles": sale.items_count})
    if settings.BOUTIQUE["NOTIFY_ADMIN_ON_SALE"]:
        discount = f" (remise {sale.discount_total})" if sale.discount_total else ""
        notify_admins(
            Notification.Type.SALE, f"Vente {sale.number}",
            f"{cashier} a encaissé {sale.total} {settings.BOUTIQUE['CURRENCY']}{discount} "
            f"– {sale.get_payment_method_display()}.",
            data={"sale_id": sale.pk, "number": sale.number}, exclude=cashier,
        )
    return sale, True


@transaction.atomic
def _create_sale_atomic(cashier, lines, payment_method, client_request_id, extra):
    if not lines:
        raise BusinessError({"lines": "La vente doit contenir au moins un article."})

    variants = lock_variants([line["variant"] for line in lines])
    max_discount = Decimal(settings.BOUTIQUE["CASHIER_MAX_DISCOUNT_PERCENT"])

    prepared = []
    for index, line in enumerate(lines, start=1):
        variant = variants.get(line["variant"])
        if variant is None:
            raise BusinessError({"lines": f"Ligne {index} : article introuvable."})
        if not variant.is_active or variant.article.is_archived:
            raise BusinessError({"lines": f"Ligne {index} : « {variant} » n'est plus en vente."})

        quantity = int(line["quantity"])
        unit_price = money(variant.effective_price)
        gross = money(unit_price * quantity)
        discount = money(line.get("discount_amount") or 0)
        reason = (line.get("discount_reason") or "").strip()

        if discount < 0 or discount > gross:
            raise BusinessError({"lines": f"Ligne {index} : la remise doit être comprise entre 0 et {gross}."})
        if discount and not reason:
            raise BusinessError({"lines": f"Ligne {index} : indiquez le motif de la remise."})
        if discount and not cashier.is_admin and discount > money(gross * max_discount / 100):
            raise BusinessError({"lines": f"Ligne {index} : remise supérieure à {max_discount} % "
                                          "— seul l'administrateur peut l'accorder."})
        prepared.append((variant, quantity, unit_price, gross, discount, reason))

    sale = Sale.objects.create(
        cashier=cashier, payment_method=payment_method,
        **({"client_request_id": client_request_id} if client_request_id else {}),
        payment_reference=extra.get("payment_reference", ""), customer_name=extra.get("customer_name", ""),
        customer_phone=extra.get("customer_phone", ""), note=extra.get("note", ""),
    )
    sale.number = f"V{timezone.localtime(sale.created_at):%Y%m%d}-{sale.pk:05d}"

    subtotal = discount_total = Decimal("0")
    for variant, quantity, unit_price, gross, discount, reason in prepared:
        SaleLine.objects.create(
            sale=sale, variant=variant, article_name=variant.article.name, variant_label=str(variant),
            sku=variant.sku, quantity=quantity, unit_price=unit_price, unit_cost=variant.article.purchase_price,
            discount_amount=discount, discount_reason=reason, line_total=gross - discount,
        )
        apply_movement(variant, StockMovement.Type.SALE, quantity, cashier,
                       reason=f"Vente {sale.number}", sale=sale)
        subtotal += gross
        discount_total += discount

    sale.subtotal, sale.discount_total, sale.total = subtotal, discount_total, subtotal - discount_total

    received = extra.get("amount_received")
    if received is not None:
        received = money(received)
        if received < sale.total:
            raise BusinessError({"amount_received": f"Montant reçu insuffisant : {sale.total} attendu."})
        sale.amount_received = received
        sale.change_due = received - sale.total if payment_method == PaymentMethod.CASH else Decimal("0")
    sale.save()
    return sale


def cancel_sale(sale, *, user, reason, request=None):
    """Annule une vente et remet les articles en stock (réservé à l'administrateur)."""
    if not reason or not reason.strip():
        raise BusinessError({"reason": "Le motif d'annulation est obligatoire."})
    with transaction.atomic():
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if sale.status == Sale.Status.CANCELLED:
            raise BusinessError({"detail": "Cette vente est déjà annulée."})
        lines = list(sale.lines.select_related("variant"))
        lock_variants([line.variant_id for line in lines])
        for line in lines:
            apply_movement(line.variant, StockMovement.Type.SALE_CANCEL, line.quantity, user,
                           reason=f"Annulation {sale.number} : {reason}", sale=sale)
        sale.status = Sale.Status.CANCELLED
        sale.cancelled_at, sale.cancelled_by, sale.cancellation_reason = timezone.now(), user, reason.strip()
        sale.save()

    log_action(AuditLog.Action.SALE_CANCELLED, user=user, request=request, target=sale,
               details={"motif": reason, "total": str(sale.total)})
    notify_admins(
        Notification.Type.SALE_CANCELLED, f"Vente {sale.number} annulée",
        f"{user} a annulé la vente {sale.number} ({sale.total} {settings.BOUTIQUE['CURRENCY']}) : {reason}",
        level=Notification.Level.WARNING, data={"sale_id": sale.pk}, exclude=user,
    )
    return sale


def compute_cash_summary(cashier, day):
    """Chiffres d'une journée de caisse pour un caissier (utilisés par le compte rendu)."""
    sales = Sale.objects.filter(cashier=cashier, created_at__date=day)
    done = sales.filter(status=Sale.Status.COMPLETED)
    totals = done.aggregate(total=Sum("total"), discounts=Sum("discount_total"))
    # Agrégat séparé : une jointure sur les lignes fausserait la somme des totaux.
    items = SaleLine.objects.filter(sale__in=done).aggregate(n=Sum("quantity"))["n"]
    by_payment = {
        row["payment_method"]: str(row["amount"])
        for row in done.values("payment_method").annotate(amount=Sum("total")).order_by()
    }
    counts = sales.aggregate(
        completed=Count("id", filter=Q(status=Sale.Status.COMPLETED)),
        cancelled=Count("id", filter=Q(status=Sale.Status.CANCELLED)),
    )
    return {
        "report_date": day,
        "sales_count": counts["completed"],
        "cancelled_count": counts["cancelled"],
        "items_sold": items or 0,
        "total_sales": totals["total"] or Decimal("0"),
        "total_discounts": totals["discounts"] or Decimal("0"),
        "totals_by_payment": by_payment,
        "expected_cash": Decimal(by_payment.get(PaymentMethod.CASH, "0")),
    }
