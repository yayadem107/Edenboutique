"""Outils partagés par les tests : comptes, articles et raccourcis d'appel à l'API."""

from decimal import Decimal

from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Article, ArticleVariant, Category, Color, Size
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement

PASSWORD = "Test-Mot2Passe!"


def make_user(username, role=User.Role.CASHIER, **extra):
    user = User(username=username, full_name=extra.pop("full_name", username.title()), role=role, **extra)
    user.set_password(PASSWORD)
    user.save()
    return user


class BoutiqueAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("admin", User.Role.ADMIN, full_name="Admin Test")
        cls.cashier = make_user("caissier1", full_name="Caissier Un")
        cls.other_cashier = make_user("caissier2", full_name="Caissier Deux")

        cls.parent_category = Category.objects.create(name="Vêtements fille")
        cls.category = Category.objects.create(name="Robes", parent=cls.parent_category)
        cls.size = Size.objects.create(label="4A")
        cls.size_6 = Size.objects.create(label="6A")
        cls.color = Color.objects.create(name="Rose")

        cls.article = Article.objects.create(
            reference="ROB-001", name="Robe à volants", category=cls.category,
            purchase_price=Decimal("4000"), sale_price=Decimal("10000"),
        )
        cls.variant = ArticleVariant.objects.create(
            article=cls.article, size=cls.size, color=cls.color, barcode="3700000000011", alert_threshold=2,
        )
        apply_movement(cls.variant, StockMovement.Type.PURCHASE, 10, cls.admin, reason="Stock de test")

    def setUp(self):
        cache.clear()  # remet à zéro la limitation des tentatives de connexion

    def login_as(self, user):
        self.client.force_authenticate(user=user)
        return user

    def refresh_variant(self, variant=None):
        variant = variant or self.variant
        variant.refresh_from_db()
        return variant.quantity

    def make_variant(self, quantity=5, size=None, article=None, **extra):
        variant = ArticleVariant.objects.create(article=article or self.article, size=size or self.size_6, **extra)
        if quantity:
            apply_movement(variant, StockMovement.Type.PURCHASE, quantity, self.admin, reason="Test")
        return variant

    def sell(self, lines, payment_method="CASH", **extra):
        return self.client.post("/api/sales/", {"payment_method": payment_method, "lines": lines, **extra},
                                format="json")
