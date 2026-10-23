"""
Catalogue : catégories, tranches d'âge, tailles, couleurs, fournisseurs et articles.

Principe : la catégorie commerciale, la tranche d'âge, la taille et le type
d'article sont des notions SÉPARÉES. On évite ainsi des centaines de
catégories du genre « Robes fille 4-6 ans rouge ».
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.common.models import TimeStampedModel


class ArticleType(models.TextChoices):
    CLOTHING = "CLOTHING", "Vêtement"
    UNDERWEAR = "UNDERWEAR", "Sous-vêtement"
    SHOES = "SHOES", "Chaussures"
    ACCESSORY = "ACCESSORY", "Accessoire"
    CHILDCARE = "CHILDCARE", "Puériculture et sommeil"
    FEEDING = "FEEDING", "Repas et alimentation"
    HYGIENE = "HYGIENE", "Hygiène et soins"
    SAFETY = "SAFETY", "Sorties et sécurité"
    TOY = "TOY", "Jouet et éveil"


class Gender(models.TextChoices):
    GIRL = "GIRL", "Fille"
    BOY = "BOY", "Garçon"
    UNISEX = "UNISEX", "Mixte"


class Category(TimeStampedModel):
    """Catégorie principale (parent vide) ou sous-catégorie (parent renseigné)."""

    name = models.CharField("nom", max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="children", verbose_name="catégorie parente",
    )
    default_article_type = models.CharField(
        "type d'article par défaut", max_length=20, choices=ArticleType.choices, blank=True,
        help_text="Pré-remplit le type lors de la création d'un article dans cette catégorie.",
    )
    description = models.TextField(blank=True)
    sort_order = models.PositiveSmallIntegerField("ordre d'affichage", default=0)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "catégorie"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="unique_category_name_per_parent"),
        ]

    def __str__(self):
        return f"{self.parent.name} › {self.name}" if self.parent_id else self.name

    def clean(self):
        if self.parent_id and self.parent.parent_id:
            raise ValidationError({"parent": "Deux niveaux maximum : catégorie puis sous-catégorie."})
        if self.parent_id and self.parent_id == self.pk:
            raise ValidationError({"parent": "Une catégorie ne peut pas être son propre parent."})
        # La contrainte d'unicité en base ne couvre pas les catégories sans parent (NULL).
        siblings = Category.objects.filter(parent_id=self.parent_id, name__iexact=self.name).exclude(pk=self.pk)
        if siblings.exists():
            raise ValidationError({"name": "Une catégorie porte déjà ce nom à ce niveau."})

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.parent.name}-{self.name}" if self.parent_id else self.name)
            slug, n = base, 2
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def descendant_ids(self):
        return [self.pk, *self.children.values_list("pk", flat=True)]


class AgeRange(models.Model):
    """Tranche d'âge configurable (ex. « 3–6 mois », « 4–6 ans »), exprimée en mois."""

    label = models.CharField("libellé", max_length=50, unique=True)
    min_months = models.PositiveSmallIntegerField("âge minimum (mois)")
    max_months = models.PositiveSmallIntegerField("âge maximum (mois)")
    sort_order = models.PositiveSmallIntegerField("ordre d'affichage", default=0)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "tranche d'âge"
        verbose_name_plural = "tranches d'âge"
        ordering = ["sort_order", "min_months"]

    def __str__(self):
        return self.label

    def clean(self):
        if self.max_months < self.min_months:
            raise ValidationError({"max_months": "L'âge maximum doit être supérieur à l'âge minimum."})
        if self.max_months > 15 * 12:
            raise ValidationError({"max_months": "La boutique couvre les enfants jusqu'à 15 ans (180 mois)."})


class Size(models.Model):
    """Taille réelle de l'étiquette (distincte de l'âge, car elle varie selon les marques)."""

    class System(models.TextChoices):
        AGE = "AGE", "Taille en âge (3M, 4A…)"
        HEIGHT = "HEIGHT", "Taille en cm (86, 104…)"
        SHOES = "SHOES", "Pointure"
        ONE_SIZE = "ONE_SIZE", "Taille unique"
        OTHER = "OTHER", "Autre"

    label = models.CharField("libellé", max_length=20)
    system = models.CharField("système", max_length=10, choices=System.choices, default=System.AGE)
    sort_order = models.PositiveSmallIntegerField("ordre d'affichage", default=0)

    class Meta:
        verbose_name = "taille"
        ordering = ["system", "sort_order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["system", "label"], name="unique_size_per_system"),
        ]

    def __str__(self):
        return self.label


class Color(models.Model):
    name = models.CharField("nom", max_length=50, unique=True)
    hex_code = models.CharField("code couleur", max_length=7, blank=True, help_text="ex. #FF0000")

    class Meta:
        verbose_name = "couleur"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Supplier(TimeStampedModel):
    name = models.CharField("nom", max_length=150, unique=True)
    contact_name = models.CharField("contact", max_length=150, blank=True)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField("adresse", blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "fournisseur"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Article(TimeStampedModel):
    """
    Fiche article (ex. « Robe à volants »). Le stock est tenu au niveau des
    variantes (taille × couleur), voir ArticleVariant.
    """

    name = models.CharField("nom", max_length=150)
    reference = models.CharField("référence", max_length=50, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="articles", verbose_name="catégorie"
    )
    article_type = models.CharField(
        "type d'article", max_length=20, choices=ArticleType.choices, default=ArticleType.CLOTHING
    )
    gender = models.CharField("genre", max_length=10, choices=Gender.choices, default=Gender.UNISEX)
    age_ranges = models.ManyToManyField(
        AgeRange, blank=True, related_name="articles", verbose_name="tranches d'âge"
    )
    brand = models.CharField("marque", max_length=100, blank=True)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="articles", verbose_name="fournisseur",
    )
    description = models.TextField(blank=True)
    material = models.CharField("matière", max_length=150, blank=True)
    care_instructions = models.CharField("entretien", max_length=255, blank=True)
    image = models.ImageField(upload_to="articles/%Y/%m/", blank=True)

    purchase_price = models.DecimalField("prix d'achat", max_digits=12, decimal_places=2)
    sale_price = models.DecimalField("prix de vente", max_digits=12, decimal_places=2)

    # Produits soumis à des exigences particulières (jouets, puériculture, sécurité…)
    is_regulated = models.BooleanField(
        "soumis à réglementation", default=False,
        help_text="Si coché : norme obligatoire et numéro de lot exigé à chaque réception.",
    )
    safety_standard = models.CharField(
        "norme / conformité", max_length=150, blank=True, help_text="ex. CE – EN 71-1, EN 14350"
    )
    safety_warnings = models.TextField("avertissements de sécurité", blank=True)
    min_age_months = models.PositiveSmallIntegerField(
        "âge minimum recommandé (mois)", null=True, blank=True
    )
    attributes = models.JSONField(
        "caractéristiques spécifiques", default=dict, blank=True,
        help_text='Caractéristiques libres, ex. {"contenance_ml": 250, "sans_bpa": true}',
    )

    is_archived = models.BooleanField("archivé", default=False, db_index=True)
    archived_at = models.DateTimeField("archivé le", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="créé par",
    )

    class Meta:
        verbose_name = "article"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=models.Q(purchase_price__gte=0), name="article_purchase_price_positive"),
            models.CheckConstraint(condition=models.Q(sale_price__gte=0), name="article_sale_price_positive"),
        ]

    def __str__(self):
        return f"{self.reference} – {self.name}"

    def clean(self):
        if self.is_regulated and not self.safety_standard:
            raise ValidationError(
                {"safety_standard": "La norme est obligatoire pour un produit soumis à réglementation."}
            )


class ArticleVariant(TimeStampedModel):
    """Déclinaison réellement stockée et vendue : un article dans une taille et une couleur."""

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, related_name="variants", verbose_name="article"
    )
    size = models.ForeignKey(
        Size, on_delete=models.PROTECT, null=True, blank=True, related_name="variants", verbose_name="taille"
    )
    color = models.ForeignKey(
        Color, on_delete=models.PROTECT, null=True, blank=True, related_name="variants", verbose_name="couleur"
    )
    sku = models.CharField(
        "code article (SKU)", max_length=64, unique=True, blank=True,
        help_text="Généré automatiquement s'il est laissé vide.",
    )
    barcode = models.CharField("code-barres", max_length=64, unique=True, null=True, blank=True)
    price_override = models.DecimalField(
        "prix de vente spécifique", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Laisser vide pour utiliser le prix de l'article.",
    )
    # Modifiée UNIQUEMENT par apps.inventory.services (mouvements de stock).
    quantity = models.IntegerField("quantité en stock", default=0, editable=False)
    alert_threshold = models.PositiveIntegerField("seuil d'alerte", default=2)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "variante"
        ordering = ["article__name", "size__sort_order", "color__name"]
        constraints = [
            models.UniqueConstraint(fields=["article", "size", "color"], name="unique_variant_per_article"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="variant_quantity_not_negative"),
        ]

    def __str__(self):
        details = " / ".join(str(x) for x in (self.size, self.color) if x)
        return f"{self.article.name} ({details})" if details else self.article.name

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.article.sale_price

    @property
    def stock_status(self):
        if self.quantity <= 0:
            return "OUT"
        if self.quantity <= self.alert_threshold:
            return "LOW"
        return "OK"

    def clean(self):
        duplicates = ArticleVariant.objects.filter(
            article_id=self.article_id, size_id=self.size_id, color_id=self.color_id
        ).exclude(pk=self.pk)
        if self.article_id and duplicates.exists():
            raise ValidationError("Cette combinaison taille / couleur existe déjà pour cet article.")

    def save(self, *args, **kwargs):
        if not self.barcode:
            self.barcode = None
        if not self.sku:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def _generate_sku(self):
        parts = [self.article.reference, self.size.label if self.size else "", self.color.name[:3] if self.color else ""]
        base = slugify("-".join(p for p in parts if p)).upper()[:58] or "ART"
        sku, n = base, 2
        while ArticleVariant.objects.filter(sku=sku).exclude(pk=self.pk).exists():
            sku, n = f"{base}-{n}", n + 1
        return sku
