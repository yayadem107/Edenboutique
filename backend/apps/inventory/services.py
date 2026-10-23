"""
Seul point d'entrée autorisé pour modifier une quantité en stock.

Chaque appel :
1. verrouille la ligne de la variante (SELECT … FOR UPDATE) pour que deux
   ventes simultanées ne puissent pas vendre la même dernière pièce ;
2. refuse tout stock négatif ;
3. enregistre le mouvement avec le stock avant / après ;
4. crée les alertes « stock faible » et « rupture » au moment où le seuil est franchi.
"""

from django.db import transaction
from django.db.models import F

from apps.catalog.models import ArticleVariant
from apps.common.exceptions import BusinessError
from apps.notifications.models import Notification
from apps.notifications.services import notify_admins

from .models import StockMovement


def lock_variants(variant_ids):
    """Verrouille plusieurs variantes dans un ordre fixe (évite les blocages mutuels)."""
    return {
        v.pk: v
        for v in ArticleVariant.objects.select_for_update()
        .select_related("article")
        .filter(pk__in=sorted(set(variant_ids)))
        .order_by("pk")
    }


@transaction.atomic
def apply_movement(variant, movement_type, quantity, user, *, reason="", lot_number="",
                   unit_cost=None, sale=None):
    if quantity is None or int(quantity) <= 0:
        raise BusinessError({"quantity": "La quantité doit être supérieure à zéro."})
    quantity = int(quantity)

    variant_id = variant.pk if isinstance(variant, ArticleVariant) else variant
    locked = ArticleVariant.objects.select_for_update().select_related("article").get(pk=variant_id)

    incoming = movement_type in StockMovement.INCOMING
    delta = quantity if incoming else -quantity
    before = locked.quantity
    after = before + delta
    if after < 0:
        raise BusinessError(
            {"quantity": f"Stock insuffisant pour « {locked} » : {before} disponible(s), {quantity} demandé(s)."}
        )

    movement = StockMovement.objects.create(
        variant=locked, movement_type=movement_type, quantity=quantity, delta=delta,
        quantity_before=before, quantity_after=after, reason=reason, lot_number=lot_number,
        unit_cost=unit_cost, sale=sale, user=user,
    )
    ArticleVariant.objects.filter(pk=locked.pk).update(quantity=F("quantity") + delta)
    locked.quantity = after

    if not incoming:
        _send_stock_alerts(locked, before, after)
    return movement


def _send_stock_alerts(variant, before, after):
    data = {"variant_id": variant.pk, "article_id": variant.article_id, "quantity": after}
    if after == 0 < before:
        notify_admins(
            Notification.Type.OUT_OF_STOCK, "Rupture de stock",
            f"« {variant} » (SKU {variant.sku}) n'est plus en stock.",
            level=Notification.Level.DANGER, data=data,
        )
    elif 0 < after <= variant.alert_threshold < before:
        notify_admins(
            Notification.Type.LOW_STOCK, "Stock faible",
            f"Il reste {after} pièce(s) de « {variant} » (seuil : {variant.alert_threshold}).",
            level=Notification.Level.WARNING, data=data,
        )
