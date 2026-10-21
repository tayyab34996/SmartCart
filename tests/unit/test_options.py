"""Check one-product evaluation before adding selection among alternatives."""

import json
import sys
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.optimization.options import evaluate_product_option


class ProductOptionTests(unittest.TestCase):
    def setUp(self):
        self.product = {
            "id": "sim_chicken_250g", "ingredient_id": "chicken_breast",
            "pack_amount": "250", "pack_unit": "g", "price_minor": 45000,
            "currency": "PKR", "available": True,
        }

    def evaluate(self, required="600", pantry="200", ingredient="chicken_breast", unit="g"):
        before = deepcopy(self.product)
        try:
            return evaluate_product_option(ingredient, Decimal(required), Decimal(pantry), unit, self.product)
        finally:
            self.assertEqual(self.product, before, "Evaluation must not modify catalog records")

    def test_worked_example_has_expected_values_types_and_output_keys(self):
        actual = self.evaluate()
        self.assertEqual(actual, {
            "product_id": "sim_chicken_250g", "missing_amount": Decimal("400"),
            "pack_count": 2, "line_cost_minor": 90000, "surplus_amount": Decimal("100"),
            "unit": "g", "currency": "PKR",
        })
        self.assertIs(type(actual["pack_count"]), int)
        self.assertIs(type(actual["line_cost_minor"]), int)
        self.assertIsInstance(actual["missing_amount"], Decimal)
        self.assertIsInstance(actual["surplus_amount"], Decimal)

    def test_zero_demand_and_sufficient_pantry_produce_no_purchase(self):
        for required, pantry in (("600", "600"), ("600", "800"), ("0", "0")):
            with self.subTest(required=required, pantry=pantry):
                actual = self.evaluate(required, pantry)
                for key in ("missing_amount", "pack_count", "line_cost_minor", "surplus_amount"):
                    self.assertEqual(actual[key], 0)

    def test_wrong_ingredient_is_rejected(self):
        with self.assertRaises(ValueError):
            self.evaluate(ingredient="rice")

    def test_incompatible_units_are_rejected(self):
        for unit in ("ml", "piece"):
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                self.evaluate(unit=unit)

    def test_unavailable_option_is_rejected_even_with_zero_demand(self):
        self.product["available"] = False
        for required in ("600", "0"):
            with self.subTest(required=required), self.assertRaises(ValueError):
                self.evaluate(required=required, pantry="0")

    def test_negative_required_and_pantry_amounts_are_rejected(self):
        for required, pantry in (("-1", "0"), ("600", "-1")):
            with self.subTest(required=required, pantry=pantry), self.assertRaises(ValueError):
                self.evaluate(required, pantry)

    def test_real_seed_options_can_be_evaluated_independently(self):
        seed = json.loads((ROOT / "data/processed/pilot/catalog.json").read_text(encoding="utf-8"))
        products = {p["id"]: p for p in seed["products"]}
        for identifier, packs, cost in (("sim_chicken_250g", 2, 90000), ("sim_chicken_500g", 1, 80000)):
            with self.subTest(product=identifier):
                self.product = deepcopy(products[identifier])
                actual = self.evaluate()
                self.assertEqual(actual["pack_count"], packs)
                self.assertEqual(actual["line_cost_minor"], cost)
                self.assertEqual(actual["surplus_amount"], Decimal("100"))


if __name__ == "__main__":
    unittest.main()
