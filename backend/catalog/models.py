from django.db import models


class Category(models.Model):
    name = models.CharField("nom", max_length=100, unique=True)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )

    class Meta:
        verbose_name = "catégorie"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField("nom", max_length=150, unique=True)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField("adresse", blank=True)

    class Meta:
        verbose_name = "fournisseur"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """Modèle de vêtement (ex. « Chemise lin »), décliné en variantes taille/couleur."""

    class Gender(models.TextChoices):
        MEN = "H", "Homme"
        WOMEN = "F", "Femme"
        KIDS = "E", "Enfant"
        UNISEX = "U", "Unisexe"

    name = models.CharField("nom", max_length=150)
    reference = models.CharField("référence", max_length=50, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    brand = models.CharField("marque", max_length=100, blank=True)
    gender = models.CharField("genre", max_length=1, choices=Gender.choices, default=Gender.UNISEX)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/", blank=True)
    purchase_price = models.DecimalField("prix d'achat", max_digits=10, decimal_places=2)
    sale_price = models.DecimalField("prix de vente", max_digits=10, decimal_places=2)
    is_active = models.BooleanField("actif", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "produit"
        ordering = ["name"]

    def __str__(self):
        return f"{self.reference} - {self.name}"


class ProductVariant(models.Model):
    """Article réellement stocké : un produit dans une taille et une couleur données."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField("taille", max_length=10)
    color = models.CharField("couleur", max_length=50)
    sku = models.CharField(max_length=64, unique=True)
    barcode = models.CharField("code-barres", max_length=64, unique=True, null=True, blank=True)
    quantity = models.PositiveIntegerField("quantité en stock", default=0, editable=False)
    alert_threshold = models.PositiveIntegerField("seuil d'alerte", default=3)

    class Meta:
        verbose_name = "variante"
        ordering = ["product__name", "size", "color"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "color"], name="unique_variant_per_product"
            )
        ]

    def __str__(self):
        return f"{self.product.name} ({self.size}, {self.color})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.alert_threshold
