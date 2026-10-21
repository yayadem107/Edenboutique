from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Category, Product, ProductVariant

from .models import StockMovement


class StockMovementTests(TestCase):
    def setUp(self):
        product = Product.objects.create(
            name="Chemise lin",
            reference="CH-001",
            category=Category.objects.create(name="Chemises"),
            purchase_price=Decimal("8000"),
            sale_price=Decimal("15000"),
        )
        self.variant = ProductVariant.objects.create(
            product=product, size="M", color="Blanc", sku="CH-001-M-BL"
        )

    def move(self, movement_type, quantity):
        StockMovement.objects.create(
            variant=self.variant, movement_type=movement_type, quantity=quantity
        )
        self.variant.refresh_from_db()

    def test_in_and_out_update_quantity(self):
        self.move(StockMovement.Type.IN, 10)
        self.move(StockMovement.Type.OUT, 3)
        self.assertEqual(self.variant.quantity, 7)

    def test_out_cannot_go_negative(self):
        self.move(StockMovement.Type.IN, 2)
        with self.assertRaises(ValidationError):
            self.move(StockMovement.Type.OUT, 5)
        self.assertEqual(self.variant.quantity, 2)

    def test_negative_adjustment(self):
        self.move(StockMovement.Type.IN, 5)
        self.move(StockMovement.Type.ADJUST, -2)
        self.assertEqual(self.variant.quantity, 3)
