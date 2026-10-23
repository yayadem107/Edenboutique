import uuid
from decimal import Decimal

from django.test import override_settings
from django.conf import settings

from apps.audit.models import AuditLog
from apps.inventory.models import StockMovement
from apps.notifications.models import Notification
from apps.sales.models import Sale

from .base import BoutiqueAPITestCase


class SaleTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.cashier)

    def test_sale_updates_stock_and_totals_are_computed_by_server(self):
        response = self.sell([{"variant": self.variant.pk, "quantity": 2, "unit_price": "1"}],
                             amount_received="25000")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["total"], "20000.00")
        self.assertEqual(response.data["change_due"], "5000.00")
        self.assertRegex(response.data["number"], r"^V\d{8}-\d{5}$")
        self.assertEqual(response.data["cashier"], self.cashier.pk)
        self.assertEqual(self.refresh_variant(), 8)
        movement = StockMovement.objects.get(sale_id=response.data["id"])
        self.assertEqual(movement.delta, -2)

    def test_insufficient_stock_saves_nothing(self):
        other = self.make_variant(quantity=1)
        response = self.sell([{"variant": self.variant.pk, "quantity": 1}, {"variant": other.pk, "quantity": 2}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(self.refresh_variant(), 10)
        self.assertEqual(self.refresh_variant(other), 1)

    def test_same_variant_on_two_lines_is_checked_against_stock(self):
        response = self.sell([{"variant": self.variant.pk, "quantity": 6}, {"variant": self.variant.pk, "quantity": 5}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.refresh_variant(), 10)

    def test_double_submission_creates_a_single_sale(self):
        request_id = str(uuid.uuid4())
        first = self.sell([{"variant": self.variant.pk, "quantity": 1}], client_request_id=request_id)
        second = self.sell([{"variant": self.variant.pk, "quantity": 1}], client_request_id=request_id)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(self.refresh_variant(), 9)

    def test_request_id_of_another_cashier_is_refused(self):
        request_id = str(uuid.uuid4())
        self.sell([{"variant": self.variant.pk, "quantity": 1}], client_request_id=request_id)
        self.login_as(self.other_cashier)
        response = self.sell([{"variant": self.variant.pk, "quantity": 1}], client_request_id=request_id)
        self.assertEqual(response.status_code, 400)

    def test_discount_requires_reason(self):
        response = self.sell([{"variant": self.variant.pk, "quantity": 1, "discount_amount": "500"}])
        self.assertEqual(response.status_code, 400)
        response = self.sell([{"variant": self.variant.pk, "quantity": 1, "discount_amount": "500",
                               "discount_reason": "Petit défaut"}])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["discount_total"], "500.00")
        self.assertEqual(response.data["total"], "9500.00")
        self.assertEqual(response.data["lines"][0]["discount_reason"], "Petit défaut")

    def test_cashier_discount_is_limited(self):
        limit = settings.BOUTIQUE["CASHIER_MAX_DISCOUNT_PERCENT"]
        too_much = str(Decimal("10000") * (limit + 1) / 100)
        line = {"variant": self.variant.pk, "quantity": 1, "discount_amount": too_much, "discount_reason": "Ami"}
        self.assertEqual(self.sell([line]).status_code, 400)
        self.login_as(self.admin)
        self.assertEqual(self.sell([line]).status_code, 201)

    def test_discount_cannot_exceed_line_amount(self):
        line = {"variant": self.variant.pk, "quantity": 1, "discount_amount": "10001", "discount_reason": "x"}
        self.login_as(self.admin)
        self.assertEqual(self.sell([line]).status_code, 400)

    def test_amount_received_must_cover_total(self):
        response = self.sell([{"variant": self.variant.pk, "quantity": 1}], amount_received="5000")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.refresh_variant(), 10)

    def test_archived_article_cannot_be_sold(self):
        self.article.is_archived = True
        self.article.save()
        self.assertEqual(self.sell([{"variant": self.variant.pk, "quantity": 1}]).status_code, 400)

    def test_empty_sale_is_refused(self):
        self.assertEqual(self.sell([]).status_code, 400)

    def test_admin_is_notified_and_sale_is_audited(self):
        response = self.sell([{"variant": self.variant.pk, "quantity": 1}])
        self.assertTrue(Notification.objects.filter(recipient=self.admin, type="SALE",
                                                    data__sale_id=response.data["id"]).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.SALE_CREATED, user=self.cashier).exists())

    def test_cashier_only_sees_own_sales(self):
        self.sell([{"variant": self.variant.pk, "quantity": 1}])
        self.login_as(self.other_cashier)
        other = self.sell([{"variant": self.variant.pk, "quantity": 1}])
        response = self.client.get("/api/sales/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], other.data["id"])
        self.login_as(self.admin)
        self.assertEqual(self.client.get("/api/sales/").data["count"], 2)

    @override_settings(BOUTIQUE={**settings.BOUTIQUE, "CASHIERS_SEE_ALL_SALES": True})
    def test_setting_lets_cashiers_see_all_sales(self):
        self.sell([{"variant": self.variant.pk, "quantity": 1}])
        self.login_as(self.other_cashier)
        self.assertEqual(self.client.get("/api/sales/").data["count"], 1)

    def test_sales_cannot_be_edited_or_deleted(self):
        sale_id = self.sell([{"variant": self.variant.pk, "quantity": 1}]).data["id"]
        self.login_as(self.admin)
        self.assertEqual(self.client.patch(f"/api/sales/{sale_id}/", {"total": "1"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(f"/api/sales/{sale_id}/").status_code, 405)

    def test_cashier_unit_cost_is_hidden(self):
        response = self.sell([{"variant": self.variant.pk, "quantity": 1}])
        self.assertNotIn("unit_cost", response.data["lines"][0])


class SaleCancellationTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.cashier)
        self.sale_id = self.sell([{"variant": self.variant.pk, "quantity": 3}]).data["id"]
        self.login_as(self.admin)

    def test_cancel_restores_stock(self):
        response = self.client.post(f"/api/sales/{self.sale_id}/cancel/", {"reason": "Erreur de caisse"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(response.data["cancellation_reason"], "Erreur de caisse")
        self.assertEqual(self.refresh_variant(), 10)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.SALE_CANCELLED).exists())

    def test_cancel_requires_reason(self):
        self.assertEqual(self.client.post(f"/api/sales/{self.sale_id}/cancel/", {}, format="json").status_code, 400)

    def test_cannot_cancel_twice(self):
        url = f"/api/sales/{self.sale_id}/cancel/"
        self.client.post(url, {"reason": "Erreur"}, format="json")
        self.assertEqual(self.client.post(url, {"reason": "Erreur"}, format="json").status_code, 400)
        self.assertEqual(self.refresh_variant(), 10)
