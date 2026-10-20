"""Regression checks for the student's pantry and whole-pack calculations."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from smartcart.optimization.packs import packs_needed
from smartcart.recipes.quantities import missing_amount


class QuantityHelperTests(unittest.TestCase):
    def test_pack_counts_round_up_and_preserve_exact_multiples(self):
        for required, pack, expected in (("400", "250", 2), ("500", "250", 2),
                                         ("501", "250", 3), ("1", "250", 1)):
            with self.subTest(required=required, pack=pack):
                actual = packs_needed(Decimal(required), Decimal(pack))
                self.assertIs(type(actual), int)
                self.assertEqual(actual, expected)

    def test_fractional_amounts_use_decimal_arithmetic(self):
        self.assertEqual(packs_needed(Decimal("0.3"), Decimal("0.1")), 3)
        self.assertEqual(missing_amount(Decimal("0.3"), Decimal("0.1")), Decimal("0.2"))

    def test_zero_demand_requires_no_packs(self):
        self.assertEqual(packs_needed(Decimal("0"), Decimal("250")), 0)

    def test_negative_demand_and_nonpositive_packs_are_rejected(self):
        for required, pack in (("-1", "250"), ("400", "0"), ("400", "-1"), ("0", "0")):
            with self.subTest(required=required, pack=pack), self.assertRaises(ValueError):
                packs_needed(Decimal(required), Decimal(pack))

    def test_pantry_stock_reduces_demand_without_negative_results(self):
        for required, pantry, expected in (("600", "200", "400"), ("600", "600", "0"),
                                           ("600", "800", "0"), ("0", "200", "0"), ("0", "0", "0")):
            with self.subTest(required=required, pantry=pantry):
                actual = missing_amount(Decimal(required), Decimal(pantry))
                self.assertIsInstance(actual, Decimal)
                self.assertEqual(actual, Decimal(expected))

    def test_negative_required_and_pantry_amounts_are_rejected(self):
        for required, pantry in (("-1", "0"), ("600", "-1")):
            with self.subTest(required=required, pantry=pantry), self.assertRaises(ValueError):
                missing_amount(Decimal(required), Decimal(pantry))

    def test_pantry_subtraction_feeds_pack_calculation(self):
        for pantry, expected_packs in (("200", 2), ("600", 0), ("800", 0)):
            with self.subTest(pantry=pantry):
                remaining = missing_amount(Decimal("600"), Decimal(pantry))
                self.assertEqual(packs_needed(remaining, Decimal("250")), expected_packs)


if __name__ == "__main__":
    unittest.main()
