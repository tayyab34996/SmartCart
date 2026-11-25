"""Phase 2 (D2): full catalog build, contract, coverage and reproducibility tests."""

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.data.catalog_build import build_catalog, pack_price_minor, parse_unit_map  # noqa: E402
from smartcart.data.contracts import ContractError, load_catalog, requirements_for, validate_catalog  # noqa: E402

CATALOG = ROOT / "data" / "processed" / "catalog.json"
PILOT = ROOT / "data" / "processed" / "pilot" / "catalog.json"
CONFIG = json.loads((ROOT / "configs" / "catalog_build.json").read_text(encoding="utf-8"))


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(CATALOG)
        cls.pilot = json.loads(PILOT.read_text(encoding="utf-8"))
        cls.products = {p["id"]: p for p in cls.catalog["products"]}
        cls.recipes = {r["id"]: r for r in cls.catalog["recipes"]}

    def test_committed_catalog_is_reproducible(self):
        rebuilt = json.dumps(build_catalog(ROOT, CONFIG), indent=2, ensure_ascii=False) + "\n"
        self.assertEqual(rebuilt, CATALOG.read_text(encoding="utf-8"))

    def test_scope_targets(self):
        result = validate_catalog(self.catalog)
        self.assertGreaterEqual(result["recipes"], 38)
        self.assertGreaterEqual(result["meal_families"], 20)
        self.assertGreaterEqual(result["products"], 300)
        self.assertLessEqual(result["products"], 500)

    def test_pilot_records_are_preserved(self):
        for product in self.pilot["products"]:
            self.assertEqual(self.products[product["id"]], product)
        for recipe in self.pilot["recipes"]:
            full = {k: v for k, v in self.recipes[recipe["id"]].items() if k != "meal_family"}
            self.assertEqual(full, recipe)

    def test_every_recipe_line_has_available_product_in_its_unit(self):
        for recipe in self.catalog["recipes"]:
            for line in recipe["ingredients"]:
                options = [p for p in self.products.values() if p["ingredient_id"] == line["ingredient_id"]
                           and p["pack_unit"] == line["unit"] and p["available"]]
                self.assertTrue(options, f"{recipe['id']}: {line['ingredient_id']} in {line['unit']}")

    def test_converted_amounts(self):
        lines = {(r, l["ingredient_id"]): l for r, rec in self.recipes.items() for l in rec["ingredients"]}
        self.assertEqual(lines[("foodcom_60350", "cheddar")]["amount"], "226.000")      # 2 cups x 113 g
        self.assertEqual(lines[("foodcom_60350", "elbow_macaroni")]["amount"], "453.593")  # 16 oz
        self.assertEqual(lines[("foodcom_133959", "green_onion")]["amount"], "6.000")  # 1 bunch policy
        self.assertEqual(lines[("foodcom_40837", "nutmeg")]["amount"], "0.617")        # 2 pinches
        self.assertEqual(lines[("foodcom_3596", "potato")]["amount"], "8.000")         # range upper bound

    def test_requirements_scale_with_servings(self):
        reqs = {r["ingredient_id"]: r for r in requirements_for(self.catalog, "foodcom_60350", 12)}
        self.assertEqual(reqs["cheddar"]["amount"], "452.000")

    def test_distractors_are_not_used_by_recipes(self):
        used = {l["ingredient_id"] for r in self.catalog["recipes"] for l in r["ingredients"]}
        for distractor in ("peanut_butter", "garlic_salt", "coconut_milk", "egg_noodles"):
            self.assertNotIn(distractor, used)
            self.assertTrue(any(p["ingredient_id"] == distractor for p in self.products.values()))

    def test_dietary_variants_and_labels(self):
        self.assertEqual(self.products["var1_soy_sauce_300ml"]["dietary"]["gluten_free"], "allowed")
        self.assertEqual(self.products["bas_soy_sauce_300ml"]["dietary"]["gluten_free"], "disallowed")
        self.assertEqual(self.products["bas_worcestershire_sauce_150ml"]["dietary"]["vegetarian"], "disallowed")
        self.assertEqual(self.products["bas_peanut_butter_340g"]["dietary"]["nut_free"], "disallowed")
        for product in self.products.values():
            self.assertTrue(set(product["dietary"].values()) <= {"allowed", "disallowed", "unknown"})

    def test_basics_products_are_always_available(self):
        for product in self.products.values():
            if product["id"].startswith("bas_"):
                self.assertTrue(product["available"], product["id"])

    def test_all_products_declare_simulation(self):
        for product in self.products.values():
            self.assertTrue(product["name"].startswith("SIMULATED "))
            self.assertEqual(product["external_ids"], {})

    def test_meal_family_is_required(self):
        broken = json.loads(json.dumps(self.catalog))
        del broken["recipes"][0]["meal_family"]
        with self.assertRaises(ContractError):
            validate_catalog(broken)

    def test_pack_price_and_unit_map_helpers(self):
        self.assertEqual(parse_unit_map("g:250|500;piece:2"), {"g": ["250", "500"], "piece": ["2"]})
        # 0.16 PKR/g x 1000 g x 0.93 discount x 1.18 brand = 175.58 -> 176 PKR
        self.assertEqual(pack_price_minor("0.16", "1000", 1, "1.18", ["1.00", "0.93"]), 17600)
        self.assertEqual(pack_price_minor("0.001", "1", 0, "1.00", ["1.00"]), 100)  # floor of 1 PKR

    def test_amounts_are_positive_decimals(self):
        for recipe in self.catalog["recipes"]:
            for line in recipe["ingredients"]:
                self.assertGreater(Decimal(line["amount"]), 0)


if __name__ == "__main__":
    unittest.main()
