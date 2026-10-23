"""
Données de DÉMONSTRATION pour développer le frontend (jamais en production).

    python manage.py seed_demo --password "UnMotDePasseDeTest"

Crée : 1 administrateur `admin`, 3 caissiers `caissier1` à `caissier3`
(tous avec le mot de passe fourni), quelques articles avec du stock et
quelques ventes. Peut être relancée : rien n'est dupliqué.
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.catalog.models import AgeRange, Article, ArticleType, ArticleVariant, Category, Color, Gender, Size
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement
from apps.sales.models import PaymentMethod, Sale
from apps.sales.services import create_sale

ARTICLES = [
    # référence, nom, (catégorie, sous-catégorie), type, genre, achat, vente, tailles, couleurs, âges, stock
    ("BOD-001", "Body manches courtes coton bio", ("Vêtements bébé (0–24 mois)", "Bodies"), ArticleType.CLOTHING,
     Gender.UNISEX, 1500, 3500, ["3M", "6M", "12M"], ["Blanc", "Jaune"], ["0–3 mois", "3–6 mois", "6–12 mois"], 6),
    ("ROB-001", "Robe à volants", ("Vêtements fille", "Robes"), ArticleType.CLOTHING, Gender.GIRL,
     4500, 9000, ["4A", "6A", "8A"], ["Rose", "Bleu ciel"], ["4–6 ans", "6–8 ans"], 4),
    ("JEA-001", "Jean coupe droite", ("Vêtements garçon", "Jeans"), ArticleType.CLOTHING, Gender.BOY,
     5000, 11000, ["6A", "8A", "10A", "12A"], ["Bleu"], ["6–8 ans", "8–10 ans", "10–12 ans"], 3),
    ("BAS-001", "Baskets à scratch", ("Chaussures", "Baskets"), ArticleType.SHOES, Gender.UNISEX,
     6000, 13500, ["24", "26", "28", "30"], ["Blanc", "Noir"], ["2–4 ans", "4–6 ans", "6–8 ans"], 2),
    ("BIB-001", "Biberon anti-colique 250 ml", ("Repas et alimentation", "Biberons"), ArticleType.FEEDING,
     Gender.UNISEX, 2500, 5500, ["Taille unique"], [], ["0–3 mois", "3–6 mois"], 10),
    ("HOC-001", "Hochet d'éveil en bois", ("Jouets et éveil", "Hochets"), ArticleType.TOY, Gender.UNISEX,
     1800, 4000, ["Taille unique"], ["Multicolore"], ["3–6 mois", "6–12 mois"], 5),
]


class Command(BaseCommand):
    help = "Crée des comptes, articles et ventes de démonstration (développement uniquement)."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Mot de passe des comptes de démonstration.")
        parser.add_argument("--force", action="store_true", help="Autoriser même si DEBUG=False.")

    @transaction.atomic
    def handle(self, *args, password, force, **options):
        if not settings.DEBUG and not force:
            raise CommandError("Refusé : DEBUG=False. Cette commande est réservée au développement.")

        call_command("init_boutique", stdout=self.stdout)

        admin = self._user("admin", "Administrateur Démo", User.Role.ADMIN, password)
        cashiers = [self._user(f"caissier{n}", f"Caissier Démo {n}", User.Role.CASHIER, password) for n in (1, 2, 3)]

        for ref, name, (parent, child), kind, gender, cost, price, sizes, colors, ages, stock in ARTICLES:
            if Article.objects.filter(reference=ref).exists():
                continue
            article = Article.objects.create(
                reference=ref, name=name, category=Category.objects.get(name=child, parent__name=parent),
                article_type=kind, gender=gender, purchase_price=cost, sale_price=price, created_by=admin,
                is_regulated=kind in (ArticleType.TOY, ArticleType.FEEDING),
                safety_standard="CE – EN 71" if kind == ArticleType.TOY else ("EN 14350" if kind == ArticleType.FEEDING else ""),
            )
            article.age_ranges.set(AgeRange.objects.filter(label__in=ages))
            for size_label in sizes:
                for color_name in colors or [None]:
                    variant = ArticleVariant.objects.create(
                        article=article, size=Size.objects.filter(label=size_label).first(),
                        color=Color.objects.get(name=color_name) if color_name else None,
                    )
                    apply_movement(variant, StockMovement.Type.PURCHASE, stock, admin,
                                   reason="Stock de démonstration", unit_cost=cost,
                                   lot_number="LOT-DEMO-001" if article.is_regulated else "")

        if not Sale.objects.exists():
            variants = list(ArticleVariant.objects.order_by("pk"))
            create_sale(cashier=cashiers[0], payment_method=PaymentMethod.CASH, amount_received=20000,
                        lines=[{"variant": variants[0].pk, "quantity": 2}, {"variant": variants[7].pk, "quantity": 1}])
            create_sale(cashier=cashiers[1], payment_method=PaymentMethod.MOBILE_MONEY, payment_reference="MM-DEMO-1",
                        lines=[{"variant": variants[-1].pk, "quantity": 1, "discount_amount": 500,
                                "discount_reason": "Client fidèle"}])

        self.stdout.write(self.style.SUCCESS(
            "Démo prête. Comptes : admin, caissier1, caissier2, caissier3 (mot de passe fourni en paramètre)."))

    def _user(self, username, full_name, role, password):
        user, created = User.objects.get_or_create(username=username, defaults={"full_name": full_name, "role": role})
        if created:
            user.set_password(password)
            user.save()
        return user
