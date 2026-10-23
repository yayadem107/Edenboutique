"""
Charge les données de référence : catégories, tranches d'âge, tailles et couleurs.

    python manage.py init_boutique

Peut être relancée sans risque : les éléments existants ne sont pas dupliqués
ni modifiés (les personnalisations faites par l'administrateur sont conservées).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import AgeRange, ArticleType, Category, Color, Size

CATEGORIES = [
    ("Vêtements bébé (0–24 mois)", ArticleType.CLOTHING,
     ["Bodies", "Pyjamas", "Grenouillères", "Brassières", "Ensembles", "Combinaisons"]),
    ("Vêtements fille", ArticleType.CLOTHING,
     ["Robes", "Jupes", "Leggings", "Pantalons", "Shorts", "Blouses", "Tee-shirts"]),
    ("Vêtements garçon", ArticleType.CLOTHING,
     ["Chemises", "Polos", "Tee-shirts", "Pantalons", "Jeans", "Shorts", "Ensembles"]),
    ("Vêtements mixtes", ArticleType.CLOTHING,
     ["Sweats", "Pulls", "Vestes", "Manteaux", "Imperméables"]),
    ("Sous-vêtements", ArticleType.UNDERWEAR,
     ["Culottes", "Boxers", "Slips", "Chaussettes", "Collants", "Maillots de corps"]),
    ("Chaussures", ArticleType.SHOES,
     ["Chaussons", "Sandales", "Baskets", "Chaussures habillées", "Bottes"]),
    ("Accessoires", ArticleType.ACCESSORY,
     ["Bonnets", "Casquettes", "Chapeaux", "Ceintures", "Sacs", "Écharpes"]),
    ("Puériculture et sommeil", ArticleType.CHILDCARE,
     ["Gigoteuses", "Couvertures", "Draps", "Bavoirs", "Langes"]),
    ("Repas et alimentation", ArticleType.FEEDING,
     ["Biberons", "Tétines", "Vaisselle enfant", "Gourdes", "Boîtes à goûter"]),
    ("Hygiène et soins", ArticleType.HYGIENE,
     ["Serviettes", "Gants de toilette", "Trousses de toilette", "Accessoires de bain"]),
    ("Sorties et sécurité", ArticleType.SAFETY,
     ["Sacs à langer", "Accessoires de poussette", "Protections adaptées"]),
    ("Jouets et éveil", ArticleType.TOY,
     ["Hochets", "Peluches", "Jouets d'éveil", "Jeux adaptés à l'âge"]),
]

# (libellé, âge min en mois, âge max en mois)
AGE_RANGES = [
    ("Naissance", 0, 1), ("0–3 mois", 0, 3), ("3–6 mois", 3, 6), ("6–12 mois", 6, 12),
    ("12–24 mois", 12, 24), ("2–4 ans", 24, 48), ("4–6 ans", 48, 72), ("6–8 ans", 72, 96),
    ("8–10 ans", 96, 120), ("10–12 ans", 120, 144), ("12–15 ans", 144, 180),
]

SIZES = {
    Size.System.AGE: ["Naissance", "1M", "3M", "6M", "9M", "12M", "18M", "24M", "2A", "3A", "4A",
                      "5A", "6A", "7A", "8A", "10A", "12A", "14A", "16A"],
    Size.System.HEIGHT: ["50", "56", "62", "68", "74", "80", "86", "92", "98", "104", "110", "116",
                         "122", "128", "134", "140", "146", "152", "158", "164"],
    Size.System.SHOES: [str(n) for n in range(16, 41)],
    Size.System.ONE_SIZE: ["Taille unique"],
}

COLORS = [
    ("Blanc", "#FFFFFF"), ("Noir", "#000000"), ("Gris", "#9E9E9E"), ("Beige", "#D8C3A5"),
    ("Marron", "#795548"), ("Rouge", "#E53935"), ("Rose", "#F48FB1"), ("Fuchsia", "#D81B60"),
    ("Orange", "#FB8C00"), ("Jaune", "#FDD835"), ("Vert", "#43A047"), ("Bleu", "#1E88E5"),
    ("Bleu ciel", "#81D4FA"), ("Bleu marine", "#1A237E"), ("Violet", "#8E24AA"),
    ("Doré", "#D4AF37"), ("Argenté", "#C0C0C0"), ("Multicolore", ""), ("Imprimé", ""),
]


class Command(BaseCommand):
    help = "Charge les catégories, tranches d'âge, tailles et couleurs par défaut."

    @transaction.atomic
    def handle(self, *args, **options):
        created = {"catégories": 0, "tranches d'âge": 0, "tailles": 0, "couleurs": 0}

        for order, (name, article_type, children) in enumerate(CATEGORIES):
            parent, new = Category.objects.get_or_create(
                name=name, parent=None, defaults={"default_article_type": article_type, "sort_order": order})
            created["catégories"] += new
            for child_order, child in enumerate(children):
                _, new = Category.objects.get_or_create(
                    name=child, parent=parent,
                    defaults={"default_article_type": article_type, "sort_order": child_order})
                created["catégories"] += new

        for order, (label, min_months, max_months) in enumerate(AGE_RANGES):
            _, new = AgeRange.objects.get_or_create(
                label=label, defaults={"min_months": min_months, "max_months": max_months, "sort_order": order})
            created["tranches d'âge"] += new

        for system, labels in SIZES.items():
            for order, label in enumerate(labels):
                _, new = Size.objects.get_or_create(system=system, label=label, defaults={"sort_order": order})
                created["tailles"] += new

        for name, hex_code in COLORS:
            _, new = Color.objects.get_or_create(name=name, defaults={"hex_code": hex_code})
            created["couleurs"] += new

        summary = ", ".join(f"{count} {label}" for label, count in created.items())
        self.stdout.write(self.style.SUCCESS(f"Données de référence chargées : {summary} ajouté(e)s."))
