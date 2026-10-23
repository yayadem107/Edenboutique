from apps.audit.models import AuditLog
from apps.notifications.models import Notification

from .base import BoutiqueAPITestCase


class NotificationTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        for n in range(3):
            Notification.objects.create(recipient=self.admin, type="SALE", title=f"Vente {n}", message="…")
        Notification.objects.create(recipient=self.cashier, type="SALE", title="Autre", message="…")
        self.login_as(self.admin)

    def test_users_only_see_their_notifications(self):
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 3)
        self.login_as(self.cashier)
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 1)

    def test_unread_count_and_mark_read(self):
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread"], 3)
        first = Notification.objects.filter(recipient=self.admin).first()
        self.assertTrue(self.client.post(f"/api/notifications/{first.pk}/mark-read/").data["is_read"])
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread"], 2)
        self.assertEqual(self.client.post("/api/notifications/mark-all-read/").data["updated"], 2)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread"], 0)

    def test_cannot_mark_someone_elses_notification(self):
        other = Notification.objects.get(recipient=self.cashier)
        self.assertEqual(self.client.post(f"/api/notifications/{other.pk}/mark-read/").status_code, 404)


class AuditTests(BoutiqueAPITestCase):
    def test_admin_actions_are_logged(self):
        self.login_as(self.admin)
        self.client.patch(f"/api/articles/{self.article.pk}/", {"sale_price": "12000"}, format="json")
        self.client.post(f"/api/articles/{self.article.pk}/archive/")
        actions = set(AuditLog.objects.filter(target_id=str(self.article.pk)).values_list("action", flat=True))
        self.assertEqual(actions, {"UPDATE", "ARCHIVE"})

    def test_audit_log_is_admin_only_and_filterable(self):
        self.login_as(self.admin)
        self.client.post(f"/api/articles/{self.article.pk}/archive/")
        response = self.client.get("/api/audit-logs/", {"action": "ARCHIVE"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "admin")
        self.login_as(self.cashier)
        self.assertEqual(self.client.get("/api/audit-logs/").status_code, 403)

    def test_audit_log_is_read_only(self):
        entry = AuditLog.objects.create(action="LOGIN", username="x")
        with self.assertRaises(ValueError):
            entry.save()
        self.login_as(self.admin)
        self.assertEqual(self.client.delete(f"/api/audit-logs/{entry.pk}/").status_code, 405)


class SystemTests(BoutiqueAPITestCase):
    def test_openapi_schema_is_generated(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/api/sales/", response.content)
