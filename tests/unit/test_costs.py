"""Check money types and the pantry-to-pack-to-cost calculation."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from smartcart.optimization.costs import line_cost_minor
from smartcart.optimization.packs import packs_needed
from smartcart.recipes.quantities import missing_amount


class LineCostTests(unittest.TestCase):
    def test_line_costs_include_zero_packs_and_free_products(self):
        for packs, price, expected in ((2, 18000, 36000), (3, 12550, 37650),
                                       (0, 18000, 0), (2, 0, 0), (0, 0, 0)):
            with self.subTest(packs=packs, price=price):
                actual = line_cost_minor(packs, price)
                self.assertIs(type(actual), int)
                self.assertEqual(actual, expected)

    def test_booleans_are_not_valid_counts_or_prices(self):
        for value in (True, False):
            with self.subTest(field="pack_count", value=value), self.assertRaises(TypeError):
                line_cost_minor(value, 18000)
            with self.subTest(field="price_minor", value=value), self.assertRaises(TypeError):
                line_cost_minor(2, value)

    def test_noninteger_types_are_rejected_before_comparison(self):
        for value in (2.0, 2.5, "2", Decimal("2"), None, [], {}):
            with self.subTest(field="pack_count", value=value), self.assertRaises(TypeError):
                line_cost_minor(value, 18000)
            with self.subTest(field="price_minor", value=value), self.assertRaises(TypeError):
                line_cost_minor(2, value)

    def test_negative_integers_are_rejected(self):
        for packs, price in ((-1, 18000), (2, -1), (-1, -1), (0, -1)):
            with self.subTest(packs=packs, price=price), self.assertRaises(ValueError):
                line_cost_minor(packs, price)

    def test_large_integer_prices_keep_their_precision(self):
        self.assertEqual(line_cost_minor(3, 9007199254740993), 27021597764222979)

    def test_pantry_to_pack_to_cost_flow(self):
        for pantry, expected in (("200", 36000), ("600", 0), ("800", 0)):
            with self.subTest(pantry=pantry):
                missing = missing_amount(Decimal("600"), Decimal(pantry))
                packs = packs_needed(missing, Decimal("250"))
                self.assertEqual(line_cost_minor(packs, 18000), expected)


if __name__ == "__main__":
    unittest.main()
