"""Deux caisses vendent la dernière pièce au même instant : une seule vente doit passer."""

import threading
import unittest

from django.db import connection
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.catalog.models import Article, ArticleVariant, Category
from apps.common.exceptions import BusinessError
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement
from apps.sales.models import Sale
from apps.sales.services import create_sale


@unittest.skipUnless(connection.vendor == "postgresql", "Nécessite PostgreSQL (verrous de ligne).")
class ConcurrentSaleTests(TransactionTestCase):
    def test_last_item_cannot_be_sold_twice(self):
        admin = User.objects.create(username="admin", full_name="Admin", role=User.Role.ADMIN)
        cashiers = [User.objects.create(username=f"c{n}", full_name=f"C{n}") for n in range(2)]
        article = Article.objects.create(reference="X-1", name="Pull", purchase_price=1, sale_price=2,
                                         category=Category.objects.create(name="Pulls"))
        variant = ArticleVariant.objects.create(article=article)
        apply_movement(variant, StockMovement.Type.PURCHASE, 1, admin, reason="Test")

        results, barrier = [], threading.Barrier(2)

        def sell(cashier):
            barrier.wait()
            try:
                create_sale(cashier=cashier, payment_method="CASH", lines=[{"variant": variant.pk, "quantity": 1}])
                results.append("ok")
            except BusinessError:
                results.append("refusée")
            finally:
                connection.close()

        threads = [threading.Thread(target=sell, args=(c,)) for c in cashiers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), ["ok", "refusée"])
        self.assertEqual(Sale.objects.count(), 1)
        variant.refresh_from_db()
        self.assertEqual(variant.quantity, 0)
