from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Article, ArticleVariant

from .base import BoutiqueAPITestCase

HEADER = "reference;nom;categorie;genre;prix_achat;prix_vente;taille;couleur;quantite\n"


def csv_file(*rows):
    return SimpleUploadedFile("import.csv", (HEADER + "\n".join(rows)).encode("utf-8"), content_type="text/csv")


class ImportTests(BoutiqueAPITestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.admin)

    def upload(self, file, **extra):
        return self.client.post("/api/articles/import/", {"file": file, **extra}, format="multipart")

    def test_import_creates_articles_variants_and_stock(self):
        response = self.upload(csv_file(
            "JUP-001;Jupe plissée;Vêtements fille > Robes;Fille;2000;5000;4A;Rose;3",
            "JUP-001;Jupe plissée;Robes;Fille;2000;5000;6A;Rose;2",
            "ROB-001;Robe à volants;Robes;Fille;4000;10000;4A;Rose;5",
        ))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["articles_created"], 1)
        self.assertEqual(response.data["articles_updated"], 1)
        self.assertEqual(response.data["units_added"], 10)
        self.assertEqual(ArticleVariant.objects.filter(article__reference="JUP-001").count(), 2)
        self.assertEqual(self.refresh_variant(), 15)

    def test_dry_run_saves_nothing(self):
        response = self.upload(csv_file("JUP-001;Jupe;Robes;Fille;2000;5000;4A;Rose;3"), dry_run="true")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertFalse(Article.objects.filter(reference="JUP-001").exists())

    def test_one_error_cancels_the_whole_import(self):
        response = self.upload(csv_file(
            "JUP-001;Jupe;Robes;Fille;2000;5000;4A;Rose;3",
            "JUP-002;Jupe;Catégorie inconnue;Fille;2000;5000;4A;Rose;3",
            "JUP-003;Jupe;Robes;Fille;abc;5000;4A;Rose;3",
        ))
        self.assertEqual(response.status_code, 400)
        self.assertEqual([e["line"] for e in response.data["errors"]], [3, 4])
        self.assertFalse(Article.objects.filter(reference="JUP-001").exists())

    def test_missing_columns(self):
        bad = SimpleUploadedFile("x.csv", b"nom;prix\nRobe;10\n", content_type="text/csv")
        self.assertEqual(self.upload(bad).status_code, 400)

    def test_template_download(self):
        response = self.client.get("/api/articles/import-template/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.decode("utf-8-sig").startswith("reference;nom;categorie"))

    def test_cashier_cannot_import(self):
        self.login_as(self.cashier)
        self.assertEqual(self.upload(csv_file("A;B;Robes;Fille;1;2;;;1")).status_code, 403)
