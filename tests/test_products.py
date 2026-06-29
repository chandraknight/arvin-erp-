"""
Tests: Product model, stock tracking, package items.

UAT flows covered:
  - Product created with category
  - ProductStock linked to product
  - Package with items
  - primary_image_url returns None when no images
"""
from decimal import Decimal

from apps.products.models import (
    Category, CategoryType, Product, ProductStock, Package, PackageItem
)
from .base import BaseERPTestCase


class ProductModelTests(BaseERPTestCase):

    def test_product_str(self):
        self.assertIn("Laptop", str(self.product))

    def test_product_category_name(self):
        self.assertEqual(self.product.category_name, "Electronics")

    def test_product_primary_image_url_none_when_no_images(self):
        self.assertIsNone(self.product.primary_image_url)

    def test_product_stock_exists(self):
        stock = ProductStock.objects.get(product=self.product)
        self.assertEqual(stock.stock, 100)
        self.assertEqual(stock.ecom_stock, 50)

    def test_product_is_not_service_by_default(self):
        self.assertFalse(self.product.is_service)


class PackageModelTests(BaseERPTestCase):

    def test_package_creation_with_items(self):
        pkg = Package.objects.create(
            company=self.company,
            name="Starter Bundle",
            price=Decimal("80000.00"),
        )
        pi = PackageItem.objects.create(
            package=pkg,
            product=self.product,
            quantity=2,
        )
        self.assertEqual(pkg.items.count(), 1)
        self.assertIn("Starter Bundle", str(pi))

    def test_package_str(self):
        pkg = Package.objects.create(
            company=self.company,
            name="Test Package",
            price=Decimal("1000.00"),
        )
        self.assertEqual(str(pkg), "Test Package")
