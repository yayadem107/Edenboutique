from .base import BoutiqueAPITestCase


class DashboardTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.cashier)
        self.sell([{"variant": self.variant.pk, "quantity": 2, "discount_amount": "1000", "discount_reason": "Fidélité"}])
        self.login_as(self.admin)
        cancelled = self.sell([{"variant": self.variant.pk, "quantity": 1}]).data["id"]
        self.client.post(f"/api/sales/{cancelled}/cancel/", {"reason": "Erreur"}, format="json")

    def test_summary_figures(self):
        data = self.client.get("/api/dashboard/summary/").data
        self.assertEqual(data["sales"]["revenue"], 19000)
        self.assertEqual(data["sales"]["sales_count"], 1)
        self.assertEqual(data["sales"]["items_sold"], 2)
        self.assertEqual(data["sales"]["discounts_total"], 1000)
        self.assertEqual(data["sales"]["cancelled_count"], 1)
        self.assertEqual(data["sales"]["gross_margin"], 11000)  # 19000 - 2 × 4000
        self.assertEqual(data["stock"]["units_in_stock"], 8)
        self.assertEqual(data["stock"]["stock_value_cost"], 32000)
        self.assertEqual(data["top_articles"][0]["quantity_sold"], 2)

    def test_cashier_does_not_see_margins_or_costs(self):
        self.login_as(self.cashier)
        data = self.client.get("/api/dashboard/summary/").data
        self.assertEqual(data["sales"]["revenue"], 19000)
        self.assertNotIn("gross_margin", data["sales"])
        self.assertNotIn("stock_value_cost", data["stock"])
        self.assertEqual(data["my_sales"]["sales_count"], 1)

    def test_periods(self):
        self.assertEqual(self.client.get("/api/dashboard/summary/", {"period": "yesterday"}).data["sales"]["sales_count"], 0)
        self.assertEqual(self.client.get("/api/dashboard/summary/", {"period": "month"}).data["sales"]["sales_count"], 1)
        self.assertEqual(self.client.get("/api/dashboard/summary/", {"period": "nimporte"}).status_code, 400)
        self.assertEqual(self.client.get("/api/dashboard/summary/", {"period": "custom"}).status_code, 400)

    def test_sales_report_series_and_csv(self):
        data = self.client.get("/api/reports/sales/", {"period": "week"}).data
        self.assertEqual(len(data["series"]), 1)
        self.assertEqual(data["series"][0]["items_sold"], 2)
        export = self.client.get("/api/reports/sales/", {"period": "week", "export": "csv"})
        self.assertEqual(export.status_code, 200)
        self.assertIn("Chiffre d'affaires", export.content.decode("utf-8-sig"))

    def test_stock_report_and_export(self):
        data = self.client.get("/api/reports/stock/").data
        self.assertEqual(data["totals"]["variants_count"], 1)
        self.assertEqual(data["by_category"][0]["category"], "Vêtements fille")
        export = self.client.get("/api/reports/stock/", {"export": "csv"}).content.decode("utf-8-sig")
        self.assertIn(self.variant.sku, export)
        self.assertIn("Prix d'achat", export)

    def test_cashier_report(self):
        rows = self.client.get("/api/reports/cashiers/").data["results"]
        cashier_row = next(r for r in rows if r["cashier_id"] == self.cashier.pk)
        self.assertEqual(cashier_row["sales_count"], 1)
        self.login_as(self.other_cashier)
        self.assertEqual(self.client.get("/api/reports/cashiers/").data["results"], [])

    def test_top_articles_csv(self):
        export = self.client.get("/api/reports/top-articles/", {"export": "csv", "period": "month"})
        self.assertIn("ROB-001", export.content.decode("utf-8-sig"))
