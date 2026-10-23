from io import StringIO

from django.core.management import call_command

from apps.catalog.models import AgeRange, Article, Category, Size
from apps.inventory.models import StockMovement

from .base import BoutiqueAPITestCase


class ArticleTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.admin)

    def article_payload(self, **extra):
        return {"name": "Robe d'été", "reference": "ROB-002", "category": self.category.pk,
                "purchase_price": "3000", "sale_price": "7000", "gender": "GIRL", **extra}

    def test_create_article_with_variants_and_initial_stock(self):
        payload = self.article_payload(initial_variants=[
            {"size": self.size.pk, "color": self.color.pk, "initial_quantity": 4},
            {"size": self.size_6.pk, "initial_quantity": 0},
        ])
        response = self.client.post("/api/articles/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        article = Article.objects.get(reference="ROB-002")
        self.assertEqual(article.variants.count(), 2)
        self.assertEqual(StockMovement.objects.filter(variant__article=article).count(), 1)
        self.assertEqual(self.client.get(f"/api/articles/{article.pk}/").data["total_quantity"], 4)

    def test_regulated_article_requires_standard(self):
        response = self.client.post("/api/articles/", self.article_payload(is_regulated=True), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("safety_standard", response.data)

    def test_negative_price_is_refused(self):
        response = self.client.post("/api/articles/", self.article_payload(sale_price="-1"), format="json")
        self.assertEqual(response.status_code, 400)

    def test_filters(self):
        age = AgeRange.objects.create(label="4–6 ans", min_months=48, max_months=72)
        self.article.age_ranges.add(age)
        self.assertEqual(self.client.get("/api/articles/", {"category": self.parent_category.pk}).data["count"], 1)
        self.assertEqual(self.client.get("/api/articles/", {"age_months": 60}).data["count"], 1)
        self.assertEqual(self.client.get("/api/articles/", {"age_months": 12}).data["count"], 0)
        self.assertEqual(self.client.get("/api/articles/", {"stock_status": "OUT"}).data["count"], 0)
        self.assertEqual(self.client.get("/api/articles/", {"search": "volants"}).data["count"], 1)
        self.assertEqual(self.client.get("/api/articles/", {"search": self.variant.barcode}).data["count"], 1)

    def test_lookup_by_barcode_or_sku(self):
        response = self.client.get("/api/variants/lookup/", {"code": "3700000000011"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.variant.pk)
        self.assertEqual(self.client.get("/api/variants/lookup/", {"code": self.variant.sku.lower()}).status_code, 200)
        self.assertEqual(self.client.get("/api/variants/lookup/", {"code": "inconnu"}).status_code, 404)

    def test_archive_hides_article_and_restore(self):
        self.client.post(f"/api/articles/{self.article.pk}/archive/")
        self.assertEqual(self.client.get("/api/articles/").data["count"], 0)
        self.assertEqual(self.client.get("/api/articles/", {"is_archived": "true"}).data["count"], 1)
        self.client.post(f"/api/articles/{self.article.pk}/restore/")
        self.assertEqual(self.client.get("/api/articles/").data["count"], 1)

    def test_article_with_history_cannot_be_deleted(self):
        response = self.client.delete(f"/api/articles/{self.article.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Article.objects.filter(pk=self.article.pk).exists())

    def test_duplicate_variant_is_refused(self):
        response = self.client.post("/api/variants/", {"article": self.article.pk, "size": self.size.pk,
                                                       "color": self.color.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_sku_is_generated(self):
        response = self.client.post("/api/variants/", {"article": self.article.pk, "size": self.size_6.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["sku"], "ROB-001-6A")
        self.assertEqual(response.data["quantity"], 0)

    def test_low_stock_list(self):
        self.make_variant(quantity=1)
        self.assertEqual(self.client.get("/api/variants/low-stock/").data["count"], 1)


class CategoryTests(BoutiqueAPITestCase):
    def test_tree(self):
        self.login_as(self.cashier)
        tree = self.client.get("/api/categories/tree/").data
        self.assertEqual(tree[0]["name"], "Vêtements fille")
        self.assertEqual(tree[0]["children"][0]["name"], "Robes")

    def test_only_two_levels(self):
        self.login_as(self.admin)
        response = self.client.post("/api/categories/", {"name": "Robes longues", "parent": self.category.pk},
                                    format="json")
        self.assertEqual(response.status_code, 400)

    def test_category_in_use_cannot_be_deleted(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.delete(f"/api/categories/{self.category.pk}/").status_code, 409)

    def test_init_boutique_is_idempotent(self):
        call_command("init_boutique", stdout=StringIO())
        counts = (Category.objects.count(), AgeRange.objects.count(), Size.objects.count())
        call_command("init_boutique", stdout=StringIO())
        self.assertEqual(counts, (Category.objects.count(), AgeRange.objects.count(), Size.objects.count()))
        # 12 catégories principales (« Vêtements fille » existait déjà dans les données de test).
        self.assertEqual(Category.objects.filter(parent__isnull=True).count(), 12)
        self.assertTrue(AgeRange.objects.filter(label="12–15 ans", max_months=180).exists())
