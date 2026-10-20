"""Check source normalization and reject invalid catalog/recipe relationships."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.data.contracts import ContractError, load_pilot, requirements_for, validate_pilot


class PilotContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = load_pilot(ROOT / "data/processed/pilot/catalog.json")

    def test_source_checked_seed_has_complete_product_coverage(self):
        result = validate_pilot(self.seed)
        self.assertEqual(result["products"], 20)
        self.assertEqual(result["recipes"], 3)
        self.assertEqual(result["covered_recipe_lines"], 12)
        self.assertEqual(result["independent_recipe_reviews_pending"], 3)
        self.assertTrue(all(p["external_ids"] == {} for p in self.seed["products"]))
        self.assertTrue(all(set(p["dietary"].values()) == {"unknown"} for p in self.seed["products"]))

    def test_duplicate_ids_and_unknown_fields_are_rejected(self):
        for section in ("sources", "ingredients", "conversions", "products", "recipes"):
            data = copy.deepcopy(self.seed)
            data[section].append(copy.deepcopy(data[section][0]))
            with self.subTest(section=section), self.assertRaisesRegex(ContractError, "duplicate ID"):
                validate_pilot(data)
        data = copy.deepcopy(self.seed)
        data["products"][0]["price"] = 450
        with self.assertRaisesRegex(ContractError, "extra fields"):
            validate_pilot(data)

    def test_prices_currency_and_simulation_provenance_are_enforced(self):
        for field, value in (("price_minor", -1), ("price_minor", 1.5),
                             ("price_minor", True), ("currency", "USD"),
                             ("simulated_fields", []), ("external_ids", {"instacart": "unverified"})):
            data = copy.deepcopy(self.seed)
            data["products"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                validate_pilot(data)

    def test_invalid_pack_amounts_and_fractional_piece_packs_are_rejected(self):
        for value in ("0", "-1", "NaN", "Infinity", 250, {}):
            data = copy.deepcopy(self.seed)
            data["products"][0]["pack_amount"] = value
            with self.subTest(value=value), self.assertRaises(ContractError):
                validate_pilot(data)
        data = copy.deepcopy(self.seed)
        next(p for p in data["products"] if p["id"] == "sim_chicken_2piece")["pack_amount"] = "1.5"
        with self.assertRaisesRegex(ContractError, "whole pieces"):
            validate_pilot(data)

    def test_mass_products_cannot_cover_count_requirements(self):
        data = copy.deepcopy(self.seed)
        data["products"] = [p for p in data["products"] if p["id"] != "sim_chicken_2piece"]
        with self.assertRaisesRegex(ContractError, "no available product covers chicken_breast in piece"):
            validate_pilot(data)

    def test_flour_reference_cannot_become_a_universal_density(self):
        for restriction in (None, "salsa"):
            data = copy.deepcopy(self.seed)
            next(c for c in data["conversions"] if c["id"] == "flour_cup_g")["ingredient_id"] = restriction
            with self.subTest(restriction=restriction), self.assertRaises(ContractError):
                validate_pilot(data)

    def test_broken_recipe_quantities_and_references_are_rejected(self):
        for field, value in (("amount", "1000"), ("source_amount", "some"),
                             ("conversion_id", "unknown"), ("unit", "ml"), ("ingredient_id", [])):
            data = copy.deepcopy(self.seed)
            data["recipes"][0]["ingredients"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_pilot(data)

    def test_invalid_dietary_states_do_not_become_permission(self):
        for value in (True, "safe", [], None):
            data = copy.deepcopy(self.seed)
            data["products"][0]["dietary"]["vegan"] = value
            with self.subTest(value=value), self.assertRaises(ContractError):
                validate_pilot(data)

    def test_source_amounts_scale_without_accumulating_rounding(self):
        values = {r["ingredient_id"]: r for r in requirements_for(self.seed, "foodcom_3474", 2)}
        self.assertEqual(values["white_flour"]["amount"], "120.000")
        self.assertEqual(values["egg"]["amount"], "1.000")
        self.assertEqual(values["olive_oil"]["amount"], "7.394")
        self.assertEqual(values["water"]["amount"], "29.574")
        seven = {r["ingredient_id"]: r for r in requirements_for(self.seed, "foodcom_3474", 7)}
        self.assertEqual(seven["olive_oil"]["amount"], "25.877")
        self.assertEqual(seven["water"]["amount"], "103.508")

    def test_source_package_multiplier_and_piece_counts_are_preserved(self):
        quesadilla = {r["ingredient_id"]: r for r in requirements_for(self.seed, "foodcom_3978", 10)}
        self.assertEqual(quesadilla["salsa"]["amount"], "453.593")
        self.assertEqual(quesadilla["chicken_breast"]["amount"], "453.593")
        self.assertEqual(quesadilla["cheddar"]["amount"], "226.797")
        honey = {r["ingredient_id"]: r for r in requirements_for(self.seed, "foodcom_19090", 4)}
        self.assertEqual(honey["chicken_breast"], {"ingredient_id": "chicken_breast", "amount": "4.000", "unit": "piece"})

    def test_invalid_serving_counts_and_unknown_recipes_fail_explicitly(self):
        for servings in (0, -1, True, 2.5):
            with self.subTest(servings=servings), self.assertRaises(ContractError):
                requirements_for(self.seed, "foodcom_3474", servings)
        with self.assertRaisesRegex(ContractError, "Unknown recipe"):
            requirements_for(self.seed, "not_a_recipe", 2)

    def test_cli_rejects_invalid_seed_without_a_traceback(self):
        data = copy.deepcopy(self.seed)
        data["products"][0]["price_minor"] = -1
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_pilot.py"), "--data", str(path)],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["valid"])
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
