from apps.inventory.models import StockMovement
from apps.notifications.models import Notification

from .base import BoutiqueAPITestCase


class StockMovementTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.admin)

    def move(self, movement_type, quantity, **extra):
        return self.client.post("/api/stock-movements/", {"variant": self.variant.pk, "movement_type": movement_type,
                                                          "quantity": quantity, **extra}, format="json")

    def test_purchase_increases_stock_and_records_history(self):
        response = self.move("PURCHASE", 5)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["quantity_before"], 10)
        self.assertEqual(response.data["quantity_after"], 15)
        self.assertEqual(self.refresh_variant(), 15)

    def test_outgoing_movement_requires_reason(self):
        self.assertEqual(self.move("LOSS", 1).status_code, 400)
        self.assertEqual(self.move("LOSS", 1, reason="Article taché").status_code, 201)
        self.assertEqual(self.refresh_variant(), 9)

    def test_stock_can_never_be_negative(self):
        response = self.move("LOSS", 11, reason="Vol")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Stock insuffisant", str(response.data))
        self.assertEqual(self.refresh_variant(), 10)

    def test_sale_types_cannot_be_entered_manually(self):
        self.assertEqual(self.move("SALE", 1, reason="x").status_code, 400)
        self.assertEqual(self.move("SALE_CANCEL", 1, reason="x").status_code, 400)

    def test_regulated_article_requires_lot_number(self):
        self.article.is_regulated, self.article.safety_standard = True, "EN 71"
        self.article.save()
        self.assertEqual(self.move("PURCHASE", 3).status_code, 400)
        self.assertEqual(self.move("PURCHASE", 3, lot_number="LOT-42").status_code, 201)

    def test_inventory_count_creates_adjustment(self):
        url = "/api/stock-movements/inventory-count/"
        response = self.client.post(url, {"variant": self.variant.pk, "counted_quantity": 7}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["movement_type"], "ADJUST_OUT")
        self.assertEqual(self.refresh_variant(), 7)
        exact = self.client.post(url, {"variant": self.variant.pk, "counted_quantity": 7}, format="json")
        self.assertEqual(exact.status_code, 200)
        self.assertEqual(StockMovement.objects.filter(movement_type="ADJUST_OUT").count(), 1)

    def test_reception_is_all_or_nothing(self):
        other = self.make_variant(quantity=0)
        response = self.client.post("/api/stock-movements/reception/", {
            "reason": "Livraison n°1",
            "lines": [{"variant": self.variant.pk, "quantity": 5}, {"variant": other.pk, "quantity": 0}],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.refresh_variant(), 10)
        response = self.client.post("/api/stock-movements/reception/", {
            "reason": "Livraison n°1",
            "lines": [{"variant": self.variant.pk, "quantity": 5}, {"variant": other.pk, "quantity": 3}],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.refresh_variant(), 15)
        self.assertEqual(self.refresh_variant(other), 3)

    def test_low_stock_and_out_of_stock_alerts(self):
        self.move("LOSS", 8, reason="Casse")  # 10 -> 2 : seuil atteint
        self.assertTrue(Notification.objects.filter(type="LOW_STOCK", recipient=self.admin).exists())
        self.move("LOSS", 2, reason="Casse")  # 2 -> 0 : rupture
        self.assertTrue(Notification.objects.filter(type="OUT_OF_STOCK", recipient=self.admin).exists())
        self.assertEqual(Notification.objects.filter(type="LOW_STOCK").count(), 1)

    def test_movements_are_immutable(self):
        movement = StockMovement.objects.first()
        with self.assertRaises(ValueError):
            movement.save()
        with self.assertRaises(ValueError):
            movement.delete()
        self.assertEqual(self.client.delete(f"/api/stock-movements/{movement.pk}/").status_code, 405)

    def test_history_filters_and_csv_export(self):
        self.move("LOSS", 1, reason="Casse")
        response = self.client.get("/api/stock-movements/", {"direction": "out"})
        self.assertEqual(response.data["count"], 1)
        export = self.client.get("/api/stock-movements/", {"export": "csv"})
        self.assertEqual(export["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Stock avant", export.content.decode("utf-8-sig"))
