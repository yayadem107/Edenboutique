"""Vérifie la matrice de docs/PERMISSIONS.md, côté serveur."""

from .base import BoutiqueAPITestCase


class AnonymousTests(BoutiqueAPITestCase):
    def test_everything_requires_login_except_health_and_login(self):
        self.assertEqual(self.client.get("/api/health/").status_code, 200)
        for url in ["/api/articles/", "/api/variants/", "/api/sales/", "/api/stock-movements/",
                    "/api/dashboard/summary/", "/api/reports/stock/", "/api/notifications/",
                    "/api/categories/", "/api/cash-reports/"]:
            self.assertEqual(self.client.get(url).status_code, 401, url)


class CashierPermissionTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.cashier)

    def test_can_read_catalog_and_stock(self):
        for url in ["/api/articles/", f"/api/articles/{self.article.pk}/", "/api/variants/",
                    "/api/categories/", "/api/categories/tree/", "/api/sizes/", "/api/colors/",
                    "/api/age-ranges/", "/api/stock-movements/", "/api/variants/low-stock/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_cannot_modify_catalog(self):
        url = f"/api/articles/{self.article.pk}/"
        self.assertEqual(self.client.post("/api/articles/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(url, {"sale_price": "1"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertEqual(self.client.post(f"{url}archive/").status_code, 403)
        self.assertEqual(self.client.post("/api/variants/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/categories/", {"name": "X"}, format="json").status_code, 403)

    def test_cannot_modify_stock(self):
        data = {"variant": self.variant.pk, "movement_type": "PURCHASE", "quantity": 5}
        self.assertEqual(self.client.post("/api/stock-movements/", data, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/stock-movements/inventory-count/",
                                          {"variant": self.variant.pk, "counted_quantity": 99}, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/stock-movements/reception/", {"lines": []}, format="json").status_code, 403)
        self.assertEqual(self.refresh_variant(), 10)

    def test_quantity_cannot_be_changed_through_variant(self):
        self.login_as(self.admin)
        self.client.patch(f"/api/variants/{self.variant.pk}/", {"quantity": 500}, format="json")
        self.assertEqual(self.refresh_variant(), 10)

    def test_can_record_sale_but_not_cancel(self):
        response = self.sell([{"variant": self.variant.pk, "quantity": 1}])
        self.assertEqual(response.status_code, 201)
        cancel = self.client.post(f"/api/sales/{response.data['id']}/cancel/", {"reason": "test"}, format="json")
        self.assertEqual(cancel.status_code, 403)

    def test_can_read_dashboard_and_reports(self):
        for url in ["/api/dashboard/summary/", "/api/reports/sales/", "/api/reports/top-articles/",
                    "/api/reports/stock/", "/api/reports/cashiers/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_only_areas(self):
        for url in ["/api/users/", "/api/audit-logs/", "/api/suppliers/", "/api/articles/import-template/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_purchase_prices_are_hidden(self):
        data = self.client.get(f"/api/articles/{self.article.pk}/").data
        self.assertNotIn("purchase_price", data)
        self.assertNotIn("margin", data)
        stock = self.client.get("/api/reports/stock/").data
        self.assertNotIn("stock_value_cost", stock["totals"])

    def test_admin_sees_purchase_prices(self):
        self.login_as(self.admin)
        data = self.client.get(f"/api/articles/{self.article.pk}/").data
        self.assertEqual(data["purchase_price"], "4000.00")
        self.assertEqual(data["margin"], "6000.00")
