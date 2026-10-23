from apps.notifications.models import Notification

from .base import BoutiqueAPITestCase


class CashReportTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.cashier)
        self.sell([{"variant": self.variant.pk, "quantity": 2}], payment_method="CASH")
        self.sell([{"variant": self.variant.pk, "quantity": 1}], payment_method="MOBILE_MONEY")

    def test_preview_computes_day_figures(self):
        data = self.client.get("/api/cash-reports/preview/").data
        self.assertEqual(data["sales_count"], 2)
        self.assertEqual(data["items_sold"], 3)
        self.assertEqual(data["total_sales"], "30000.00")
        self.assertEqual(data["expected_cash"], "20000.00")

    def test_submit_report_computes_difference_and_notifies_admin(self):
        response = self.client.post("/api/cash-reports/", {"counted_cash": "19500", "comment": "Il manque 500"},
                                    format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["expected_cash"], "20000.00")
        self.assertEqual(response.data["cash_difference"], "-500.00")
        self.assertTrue(Notification.objects.filter(recipient=self.admin, type="CASH_REPORT").exists())

    def test_cashier_cannot_override_computed_figures(self):
        response = self.client.post("/api/cash-reports/", {"counted_cash": "20000", "total_sales": "1"}, format="json")
        self.assertEqual(response.data["total_sales"], "30000.00")

    def test_one_report_per_day_but_it_can_be_corrected(self):
        report = self.client.post("/api/cash-reports/", {"counted_cash": "19000"}, format="json").data
        self.assertEqual(self.client.post("/api/cash-reports/", {"counted_cash": "20000"}, format="json").status_code, 400)
        response = self.client.patch(f"/api/cash-reports/{report['id']}/", {"counted_cash": "20000"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cash_difference"], "0.00")

    def test_review_by_admin_locks_report(self):
        report = self.client.post("/api/cash-reports/", {"counted_cash": "20000"}, format="json").data
        self.assertEqual(self.client.post(f"/api/cash-reports/{report['id']}/review/").status_code, 403)
        self.login_as(self.admin)
        reviewed = self.client.post(f"/api/cash-reports/{report['id']}/review/", {"admin_comment": "OK"}, format="json")
        self.assertEqual(reviewed.data["status"], "REVIEWED")
        self.login_as(self.cashier)
        response = self.client.patch(f"/api/cash-reports/{report['id']}/", {"counted_cash": "1"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_cashiers_only_see_their_reports(self):
        self.client.post("/api/cash-reports/", {"counted_cash": "20000"}, format="json")
        self.login_as(self.other_cashier)
        self.assertEqual(self.client.get("/api/cash-reports/").data["count"], 0)
        self.login_as(self.admin)
        self.assertEqual(self.client.get("/api/cash-reports/").data["count"], 1)
