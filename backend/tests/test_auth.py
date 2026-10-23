from apps.accounts.models import User
from apps.audit.models import AuditLog

from .base import PASSWORD, BoutiqueAPITestCase, make_user


class LoginTests(BoutiqueAPITestCase):
    def login(self, username="caissier1", password=PASSWORD):
        return self.client.post("/api/auth/login/", {"username": username, "password": password}, format="json")

    def test_login_returns_tokens_profile_and_capabilities(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], "CASHIER")
        self.assertTrue(response.data["user"]["capabilities"]["create_sale"])
        self.assertFalse(response.data["user"]["capabilities"]["manage_stock"])
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGIN, user=self.cashier).exists())

    def test_wrong_password_is_refused_and_logged(self):
        response = self.login(password="mauvais")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILED, username="caissier1").exists())

    def test_login_is_throttled(self):
        for _ in range(10):
            self.login(password="mauvais")
        self.assertEqual(self.login().status_code, 429)

    def test_access_token_gives_access_to_profile(self):
        token = self.login().data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "caissier1")

    def test_profile_requires_authentication(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_logout_revokes_refresh_token(self):
        tokens = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code, 204)
        response = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_refresh_returns_new_access_token(self):
        tokens = self.login().data
        response = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_deactivated_user_cannot_login(self):
        self.cashier.is_active = False
        self.cashier.save()
        self.assertEqual(self.login().status_code, 401)


class PasswordTests(BoutiqueAPITestCase):
    def test_change_password(self):
        self.login_as(self.cashier)
        bad = self.client.post("/api/auth/change-password/",
                               {"old_password": "faux", "new_password": "Nouveau-Pass-2026"}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post("/api/auth/change-password/",
                              {"old_password": PASSWORD, "new_password": "Nouveau-Pass-2026"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("access", ok.data)
        self.cashier.refresh_from_db()
        self.assertTrue(self.cashier.check_password("Nouveau-Pass-2026"))

    def test_weak_password_is_refused(self):
        self.login_as(self.cashier)
        response = self.client.post("/api/auth/change-password/",
                                    {"old_password": PASSWORD, "new_password": "1234"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_admin_reset_forces_password_change(self):
        self.login_as(self.admin)
        response = self.client.post(f"/api/users/{self.cashier.pk}/reset-password/",
                                    {"new_password": "Temporaire-2026"}, format="json")
        self.assertEqual(response.status_code, 204)
        self.cashier.refresh_from_db()
        self.assertTrue(self.cashier.must_change_password)


class UserManagementTests(BoutiqueAPITestCase):
    def test_no_public_registration(self):
        data = {"username": "pirate", "full_name": "X", "password": "Un-Pass-Solide-1"}
        self.assertEqual(self.client.post("/api/users/", data, format="json").status_code, 401)
        self.login_as(self.cashier)
        self.assertEqual(self.client.post("/api/users/", data, format="json").status_code, 403)

    def test_admin_creates_cashier_who_must_change_password(self):
        self.login_as(self.admin)
        response = self.client.post("/api/users/", {"username": "caissier3", "full_name": "Caissier Trois",
                                                    "password": "Un-Pass-Solide-1"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="caissier3")
        self.assertTrue(user.must_change_password)
        self.assertEqual(user.role, User.Role.CASHIER)
        self.assertNotIn("password", response.data)

    def test_maximum_three_active_cashiers(self):
        make_user("caissier3")
        self.login_as(self.admin)
        response = self.client.post("/api/users/", {"username": "caissier4", "full_name": "Quatre",
                                                    "password": "Un-Pass-Solide-1"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_deactivate_and_reactivate(self):
        self.login_as(self.admin)
        self.assertFalse(self.client.post(f"/api/users/{self.cashier.pk}/deactivate/").data["is_active"])
        self.assertTrue(self.client.post(f"/api/users/{self.cashier.pk}/activate/").data["is_active"])

    def test_admin_cannot_deactivate_self(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.post(f"/api/users/{self.admin.pk}/deactivate/").status_code, 400)

    def test_last_admin_cannot_be_demoted(self):
        self.login_as(self.admin)
        response = self.client.patch(f"/api/users/{self.admin.pk}/", {"role": "CASHIER"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_users_are_never_deleted(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.delete(f"/api/users/{self.cashier.pk}/").status_code, 405)
