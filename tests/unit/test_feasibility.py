"""Phase 4: gold feasibility checker cases named in BUILD_PHASES (exact enumeration)."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.validation.feasibility import check_feasibility, resolve_requirements  # noqa: E402

DIET = {"vegetarian": "allowed", "vegan": "allowed", "gluten_free": "allowed", "dairy_free": "allowed",
        "nut_free": "allowed"}


def product(pid, ingredient, amount, unit, price, available=True, **diet):
    return {"id": pid, "ingredient_id": ingredient, "pack_amount": str(amount), "pack_unit": unit,
            "price_minor": price, "currency": "PKR", "available": available, "dietary": {**DIET, **diet}}


CATALOG = {"recipes": [], "conversions": [], "products": [
    product("flour_250", "flour", 250, "g", 10000),
    product("flour_1000", "flour", 1000, "g", 35000),
    product("cheese_200", "cheese", 200, "g", 30000, vegetarian="unknown"),
    product("cheese_veg_200", "cheese", 200, "g", 42000),
    product("cheese_cheap_off", "cheese", 200, "g", 1000, available=False),
    product("egg_6", "egg", 6, "piece", 24000, vegan="disallowed"),
]}


def request(items, **kw):
    base = {"intent": "build_grocery_list", "recipe_id": None, "servings": None, "pantry": {}, "budget_minor": None,
            "diet": [], "exclusions": [], "needs_clarification": False}
    base.update(kw)
    base["items"] = [{"ingredient_id": i, "amount": str(a), "unit": u} for i, a, u in items]
    return base


class FeasibilityTests(unittest.TestCase):
    def test_worked_example_pantry_and_packs(self):
        # 600 g needed, 200 g in the pantry, 250 g packs -> 2 packs and 100 g surplus.
        result = check_feasibility(request([("flour", 600, "g")], pantry={"flour": "200"}),
                                   {**CATALOG, "products": CATALOG["products"][:1]})
        self.assertEqual(result["label"], "feasible")
        line = result["basket"][0]
        self.assertEqual((line["product_id"], line["pack_count"], line["surplus"]), ("flour_250", 2, "100.000"))
        self.assertEqual(result["min_cost_minor"], 20000)

    def test_exact_budget_is_feasible_and_one_below_is_not(self):
        req = request([("flour", 600, "g")])
        cheapest = check_feasibility(req, CATALOG)["min_cost_minor"]
        self.assertEqual(cheapest, 30000)  # 3 x 250 g (30000) beats 1 x 1000 g (35000)
        self.assertEqual(check_feasibility({**req, "budget_minor": cheapest}, CATALOG)["label"], "feasible")
        short = check_feasibility({**req, "budget_minor": cheapest - 1}, CATALOG)
        self.assertEqual((short["label"], short["reason"]), ("infeasible", "budget_below_minimum_cost"))
        self.assertEqual(short["min_cost_minor"], cheapest)  # the required budget is still reported

    def test_multi_pack_prefers_cheaper_combination(self):
        result = check_feasibility(request([("flour", 900, "g")]), CATALOG)
        self.assertEqual([(l["product_id"], l["pack_count"]) for l in result["basket"]], [("flour_1000", 1)])

    def test_excluded_ingredient_is_dropped_and_never_bought(self):
        result = check_feasibility(request([("flour", 250, "g"), ("cheese", 200, "g")], exclusions=["cheese"]),
                                   CATALOG)
        self.assertEqual(result["label"], "feasible")
        self.assertEqual({l["ingredient_id"] for l in result["basket"]}, {"flour"})
        self.assertEqual([l["ingredient_id"] for l in result["resolved"]["excluded_lines"]], ["cheese"])

    def test_unknown_dietary_label_never_satisfies_a_diet(self):
        result = check_feasibility(request([("cheese", 200, "g")], diet=["vegetarian"]), CATALOG)
        self.assertEqual(result["basket"][0]["product_id"], "cheese_veg_200")  # dearer, but allowed
        only_unknown = {**CATALOG, "products": [p for p in CATALOG["products"] if p["id"] != "cheese_veg_200"]}
        blocked = check_feasibility(request([("cheese", 200, "g")], diet=["vegetarian"]), only_unknown)
        self.assertEqual((blocked["label"], blocked["reason"]), ("infeasible", "no_eligible_option"))
        self.assertEqual(blocked["ingredients_without_option"][0]["diet_allowed"], 0)

    def test_disallowed_label_and_unavailable_product_are_ineligible(self):
        vegan = check_feasibility(request([("egg", 6, "piece")], diet=["vegan"]), CATALOG)
        self.assertEqual(vegan["label"], "infeasible")
        cheese = check_feasibility(request([("cheese", 200, "g")]), CATALOG)
        self.assertNotIn("cheese_cheap_off", [l["product_id"] for l in cheese["basket"]])

    def test_pantry_covers_everything(self):
        result = check_feasibility(request([("flour", 200, "g")], pantry={"flour": "500"}, budget_minor=0), CATALOG)
        self.assertEqual((result["label"], result["min_cost_minor"], result["basket"]), ("feasible", 0, []))
        self.assertEqual(len(result["resolved"]["covered_by_pantry"]), 1)

    def test_unmatched_pantry_key_is_reported(self):
        resolved = resolve_requirements(request([("flour", 200, "g")], pantry={"sugar": "100"}), CATALOG)
        self.assertEqual(resolved["ignored_pantry_keys"], ["sugar"])

    def test_unknown_pantry_amount_and_clarification_labels(self):
        with self.assertRaises(ValueError):
            check_feasibility(request([("flour", 200, "g")], pantry={"flour": None}), CATALOG)
        self.assertEqual(check_feasibility(request([], needs_clarification=True, clarification_type="missing_budget"),
                                           CATALOG)["label"], "clarification")
        self.assertEqual(check_feasibility({"intent": "unsupported"}, CATALOG)["label"], "unsupported")

    def test_pruned_search_equals_full_enumeration_on_catalog_recipes(self):
        catalog = json.loads((ROOT / "data" / "processed" / "catalog.json").read_text(encoding="utf-8"))
        for recipe in catalog["recipes"][:12]:
            for diet in ([], ["vegetarian"], ["gluten_free"]):
                req = {"intent": "plan_meal", "recipe_id": recipe["id"], "servings": 4, "items": [], "pantry": {},
                       "budget_minor": None, "diet": diet, "exclusions": []}
                pruned = check_feasibility(req, catalog)
                full = check_feasibility(req, catalog, prune=False)
                self.assertEqual(pruned["label"], full["label"], recipe["id"])
                self.assertEqual(pruned.get("min_cost_minor"), full.get("min_cost_minor"), recipe["id"])
                if full["label"] == "feasible":
                    self.assertEqual(full["complete_combinations_visited"],
                                     _product(full["options_per_line"]))


def _product(values):
    out = 1
    for v in values:
        out *= v
    return out


if __name__ == "__main__":
    unittest.main()
