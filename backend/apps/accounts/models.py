from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class BoutiqueUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Compte d'un membre de la boutique. Il n'existe pas d'inscription publique :
    seuls l'administrateur (ou la commande `createsuperuser`) créent des comptes.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Super administrateur"
        CASHIER = "CASHIER", "Caissier"

    role = models.CharField("rôle", max_length=10, choices=Role.choices, default=Role.CASHIER)
    full_name = models.CharField("nom complet", max_length=150)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    must_change_password = models.BooleanField(
        "doit changer son mot de passe",
        default=False,
        help_text="Activé quand l'administrateur crée le compte ou réinitialise le mot de passe.",
    )

    objects = BoutiqueUserManager()

    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "utilisateur"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name or self.username

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        # L'accès à /admin/ (interface Django) est réservé aux administrateurs.
        self.is_staff = self.role == self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_cashier(self):
        return not self.is_admin

    @property
    def capabilities(self):
        """Ce que l'utilisateur a le droit de faire — le frontend s'en sert pour afficher les menus."""
        admin = self.is_admin
        return {
            "view_catalog": True,
            "view_stock": True,
            "create_sale": True,
            "view_sales": True,
            "view_all_sales": admin,
            "view_dashboard": True,
            "view_reports": True,
            "export_reports": True,
            "submit_cash_report": True,
            "view_purchase_prices": admin,
            "manage_catalog": admin,
            "manage_stock": admin,
            "import_files": admin,
            "cancel_sale": admin,
            "manage_users": admin,
            "view_audit_log": admin,
        }
