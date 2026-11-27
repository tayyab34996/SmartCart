"""Phase 9: CP-SAT selection against the Phase 4 enumeration, statuses (including the
timeout), AND-linked pair bonuses, the validator gate, explanations, the frozen weights
and the rebuild check."""

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.explanations import PRICE_NOTE, explain  # noqa: E402
from smartcart.optimization.cpsat import minimum_cost, select_basket  # noqa: E402
from smartcart.validation.feasibility import check_feasibility  # noqa: E402
from smartcart.validation.validator import validate_basket  # noqa: E402

CONFIG = json.loads((ROOT / "configs" / "solver.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / CONFIG["data"]["catalog"]).read_text(encoding="utf-8"))
METRICS = json.loads((ROOT / CONFIG["outputs"]["metrics"]).read_text(encoding="utf-8"))
HAS_BASKETS = (ROOT / "data" / "interim" / "instacart" / "sample_order_products.csv.gz").is_file()
NO_PAIRS = (lambda a, b: 0.0)
NO_HISTORY = (lambda u, x: 0.0)
DIET = {"vegetarian": "allowed", "vegan": "allowed", "gluten_free": "allowed", "dairy_free": "allowed",
        "nut_free": "allowed"}


def product(pid, ingredient, amount, unit, price, available=True, **diet):
    return {"id": pid, "name": f"SIMULATED {ingredient} {amount} {unit}", "ingredient_id": ingredient,
            "pack_amount": str(amount), "pack_unit": unit, "price_minor": price, "currency": "PKR",
            "available": available, "dietary": {**DIET, **diet}}


SMALL = {"recipes": [], "conversions": [],
         "ingredients": [{"id": i, "name": i, "aliases": []} for i in ("flour", "cheese", "egg")],
         "products": [
             product("flour_250", "flour", 250, "g", 10000),
             product("flour_1000", "flour", 1000, "g", 35000),
             product("cheese_200", "cheese", 200, "g", 30000, vegetarian="unknown"),
             product("cheese_veg_200", "cheese", 200, "g", 42000),
             product("cheese_cheap_off", "cheese", 200, "g", 1000, available=False),
             product("egg_6", "egg", 6, "piece", 24000, vegan="disallowed"),
         ]}
SMALL_CONFIG = copy.deepcopy(CONFIG)
SMALL_CONFIG["candidates"].update(method="tfidf", top_k=2)


def request(items, **kw):
    base = {"intent": "build_grocery_list", "recipe_id": None, "servings": None, "pantry": {}, "budget_minor": None,
            "currency": "PKR", "diet": [], "exclusions": [], "user_id": None, "needs_clarification": False,
            "clarification_type": None}
    base.update(kw)
    base["items"] = [{"ingredient_id": i, "amount": str(a), "unit": u} for i, a, u in items]
    return base


def solve(req, catalog=SMALL, config=SMALL_CONFIG, **kw):
    return select_basket(req, catalog, config, pair_fn=kw.get("pair_fn", NO_PAIRS),
                         history_fn=kw.get("history_fn", NO_HISTORY))


class AgreementWithEnumerationTests(unittest.TestCase):
    """CP-SAT against the exact Phase 4 enumeration on the plan's small cases."""

    def assert_agrees(self, req, catalog=SMALL, config=SMALL_CONFIG):
        checker = check_feasibility(req, catalog)
        result = solve(req, catalog, config)
        expected = {"feasible": "valid", "infeasible": "infeasible_in_scope"}[checker["label"]]
        self.assertEqual(result["status"], expected, (req, result["reason"]))
        self.assertEqual(minimum_cost(req, catalog, config), checker["min_cost_minor"])
        if checker["label"] == "feasible":
            self.assertTrue(result["validator"]["valid"])
            self.assertEqual(result["total_cost_minor"], checker["min_cost_minor"])
        return checker, result

    def test_worked_example_pantry_and_packs(self):
        req = request([("flour", 600, "g")], pantry={"flour": "200"})
        _, result = self.assert_agrees(req)
        line = result["lines"][0]
        self.assertEqual((line["product_id"], line["pack_count"], line["surplus"]), ("flour_250", 2, "100.000"))

    def test_exact_budget_and_one_below(self):
        req = request([("flour", 600, "g")])
        cheapest = check_feasibility(req, SMALL)["min_cost_minor"]
        self.assert_agrees({**req, "budget_minor": cheapest})
        _, short = self.assert_agrees({**req, "budget_minor": cheapest - 1})
        self.assertEqual(short["reason"], "budget_below_minimum_cost")
        self.assertEqual(short["suggested_budget_minor"], cheapest)

    def test_multi_pack(self):
        _, result = self.assert_agrees(request([("flour", 1200, "g")]))  # 5 x 250 g beats 2 x 1000 g
        self.assertEqual((result["lines"][0]["product_id"], result["lines"][0]["pack_count"]), ("flour_250", 5))

    def test_excluded_ingredient(self):
        req = request([("flour", 600, "g"), ("cheese", 100, "g")], exclusions=["cheese"])
        _, result = self.assert_agrees(req)
        self.assertNotIn("cheese", {line["ingredient_id"] for line in result["purchased"]})
        self.assertEqual(result["excluded_lines"][0]["ingredient_id"], "cheese")

    def test_unknown_label_never_satisfies_a_diet(self):
        _, result = self.assert_agrees(request([("cheese", 100, "g")], diet=["vegetarian"]))
        self.assertEqual(result["purchased"][0]["product_id"], "cheese_veg_200")  # not the cheaper "unknown" one
        _, none = self.assert_agrees(request([("egg", 6, "piece")], diet=["vegan"]))
        self.assertEqual((none["status"], none["reason"]), ("infeasible_in_scope", "no_eligible_option"))

    def test_unavailable_product_is_never_an_option(self):
        _, result = self.assert_agrees(request([("cheese", 100, "g")]))
        self.assertNotEqual(result["purchased"][0]["product_id"], "cheese_cheap_off")

    def test_pantry_covers_everything(self):
        result = solve(request([("flour", 200, "g")], pantry={"flour": "250"}))
        self.assertEqual((result["status"], result["reason"], result["purchased"]), ("valid", "pantry_covers_all", []))

    def test_minimum_cost_matches_enumeration_on_real_recipes(self):
        recipes = sorted(r["id"] for r in CATALOG["recipes"])[:12]
        for rid in recipes:
            for diet in ([], ["vegetarian"], ["gluten_free"]):
                req = {**request([]), "intent": "plan_meal", "recipe_id": rid, "diet": diet}
                self.assertEqual(minimum_cost(req, CATALOG, CONFIG), check_feasibility(req, CATALOG)["min_cost_minor"],
                                 (rid, diet))


class StatusTests(unittest.TestCase):
    def test_timeout_is_never_infeasible(self):
        config = copy.deepcopy(CONFIG)
        config["solver"]["time_limit_s"] = 0.0
        recipe = CATALOG["recipes"][0]["id"]
        req = {**request([]), "intent": "plan_meal", "recipe_id": recipe, "budget_minor": 10}  # also over budget
        result = select_basket(req, CATALOG, config, pair_fn=NO_PAIRS, history_fn=NO_HISTORY)
        self.assertEqual(result["status"], "solver_timeout")
        self.assertEqual(result["solver"][-1]["solver_status"], "UNKNOWN")
        self.assertIn("not proof", explain(result, req, CATALOG)["summary"])

    def test_request_statuses(self):
        self.assertEqual(solve({**request([]), "intent": "unsupported"})["status"], "unsupported")
        clar = solve({**request([]), "needs_clarification": True, "clarification_type": "missing_budget"})
        self.assertEqual((clar["status"], clar["reason"]), ("needs_clarification", "missing_budget"))
        self.assertEqual(solve(request([]))["status"], "invalid_request")
        bad = solve({**request([]), "intent": "plan_meal", "recipe_id": "no_such_recipe"})
        self.assertEqual(bad["status"], "invalid_request")

    def test_pool_expansion_and_no_basket_in_pool(self):
        # The TF-IDF top 2 for "cheese" are the two cheapest-scoring cheeses by ID, not the vegetarian one.
        config = copy.deepcopy(SMALL_CONFIG)
        config["candidates"]["top_k"] = 1
        req = request([("cheese", 100, "g")], diet=["vegetarian"])
        pool = solve(req, config=config)
        self.assertEqual(pool["status"], "valid")
        if pool["trace"]["events"]:  # the vegetarian cheese was outside the pool: expanded, then solved
            self.assertEqual(pool["trace"]["events"][-1]["event"], "expanded_to_catalog")
            config["candidates"]["expand"] = False
            self.assertEqual(solve(req, config=config)["status"], "no_basket_in_candidate_pool")

    def test_infeasible_needs_the_whole_catalog(self):
        req = request([("flour", 600, "g")], budget_minor=100)
        result = solve(req)
        self.assertEqual(result["status"], "infeasible_in_scope")
        models = [s["model"] for s in result["solver"]]
        self.assertIn("expanded", models)  # infeasibility is proven over every eligible product
        self.assertEqual(models[-1], "minimum_cost_without_budget")


class ObjectiveTests(unittest.TestCase):
    def test_pair_bonus_uses_and_linked_booleans(self):
        req = request([("flour", 600, "g"), ("cheese", 100, "g")])
        config = copy.deepcopy(SMALL_CONFIG)
        config["candidates"]["top_k"] = 10
        config["objective"]["fixed_weights"] = {"relevance": 0.0, "history": 0.0, "pair": 50.0}
        config["objective"]["weights"] = {"cost": 0.25, "surplus": 0.0}

        def favour(a, b):  # a brand-level pair score: the dearer flour goes with the dearer cheese
            return 1.0 if {a, b} == {"flour_1000", "cheese_veg_200"} else 0.0

        result = solve(req, config=config, pair_fn=favour)
        self.assertGreater(result["objective"]["pair_variables"], 0)
        self.assertEqual({p["product_id"] for p in result["purchased"]}, {"flour_1000", "cheese_veg_200"})
        flat = solve(req, config=config, pair_fn=lambda a, b: 0.3)  # constant: no variables
        self.assertEqual(flat["objective"]["pair_variables"], 0)
        self.assertAlmostEqual(flat["objective"]["pair_constant"], 0.3)

    def test_hard_rules_stay_outside_the_objective(self):
        config = copy.deepcopy(SMALL_CONFIG)
        config["objective"]["fixed_weights"] = {"relevance": 0.0, "history": 1000.0, "pair": 0.0}

        def loves_unknown(user, product_id):
            return 1.0 if product_id == "cheese_200" else 0.0

        req = request([("cheese", 100, "g")], diet=["vegetarian"], user_id=1)
        result = solve(req, config=config, history_fn=loves_unknown)
        self.assertEqual(result["purchased"][0]["product_id"], "cheese_veg_200")

    def test_unique_reproducible_optimum(self):
        req = {**request([]), "intent": "plan_meal", "recipe_id": CATALOG["recipes"][1]["id"]}
        a = select_basket(req, CATALOG, CONFIG, pair_fn=NO_PAIRS, history_fn=NO_HISTORY)
        b = select_basket(req, CATALOG, CONFIG, pair_fn=NO_PAIRS, history_fn=NO_HISTORY)
        self.assertEqual(a["purchased"], b["purchased"])
        self.assertTrue(all(line["cheapest_option"] for line in a["lines"]))


class ValidatorGateTests(unittest.TestCase):
    def test_validator_rejects_corrupted_solver_baskets(self):
        req = {**request([]), "intent": "plan_meal", "recipe_id": CATALOG["recipes"][0]["id"],
               "diet": [], "budget_minor": None}
        result = select_basket(req, CATALOG, CONFIG, pair_fn=NO_PAIRS, history_fn=NO_HISTORY)
        good = result["purchased"]
        self.assertTrue(validate_basket(req, good, CATALOG)["valid"])
        products = {p["id"]: p for p in CATALOG["products"]}
        first = good[0]
        other = next(p for p in CATALOG["products"] if p["ingredient_id"] not in {g["ingredient_id"] for g in good})
        unavailable = next(p for p in CATALOG["products"] if not p["available"])
        corruptions = {
            "missing_ingredient": good[1:],
            "duplicate_line": good + [first],
            "unknown_product": [{**first, "product_id": "nope"}] + good[1:],
            "invalid_pack_count": [{**first, "pack_count": 0}] + good[1:],
            "line_cost_mismatch": [{**first, "line_cost_minor": first["line_cost_minor"] + 1}] + good[1:],
            "unrequested_ingredient": good + [{"product_id": other["id"], "pack_count": 1}],
            "unavailable_product": good + [{"product_id": unavailable["id"], "pack_count": 1}],
            "over_budget": None,
        }
        for kind, lines in corruptions.items():
            if lines is None:
                check = validate_basket({**req, "budget_minor": result["total_cost_minor"] - 1}, good, CATALOG)
            else:
                check = validate_basket(req, lines, CATALOG)
            self.assertFalse(check["valid"], kind)
            self.assertIn(kind, {v["type"] for v in check["violations"]}, kind)
        smaller = next((g for g in good if g["pack_count"] > 1), None)
        if smaller:
            short = [{**g, "pack_count": g["pack_count"] - 1, "line_cost_minor": (g["pack_count"] - 1)
                      * products[g["product_id"]]["price_minor"]} if g is smaller else g for g in good]
            kinds = {v["type"] for v in validate_basket(req, short, CATALOG)["violations"]}
            self.assertIn("insufficient_quantity", kinds)


class ExplanationTests(unittest.TestCase):
    def test_explanations_come_from_the_records(self):
        req = request([("cheese", 100, "g")], diet=["vegetarian"], budget_minor=50000)
        result = solve(req)
        text = explain(result, req, SMALL)
        self.assertIn(PRICE_NOTE, text["notes"])
        self.assertIn("PKR 420.00", text["lines"][0])
        self.assertIn("allowed\" for vegetarian", text["lines"][0])
        self.assertIn("PKR 80.00 left", text["summary"])
        short = solve({**req, "budget_minor": 100})
        self.assertIn("PKR 420.00", explain(short, req, SMALL)["summary"])  # the suggested budget
        self.assertEqual(explain(short, req, SMALL)["lines"], [])


class FrozenConfigTests(unittest.TestCase):
    def test_weights_follow_the_rule_and_are_recorded(self):
        grid = METRICS["selection"]["grid"]
        best = min(enumerate(grid), key=lambda ir: (-ir[1]["success"], ir[1]["cost_ratio"], ir[1]["surplus_share"],
                                                    ir[0]))[1]
        self.assertEqual({"cost": best["cost"], "surplus": best["surplus"]}, CONFIG["selection"]["selected"])
        self.assertEqual(CONFIG["objective"]["weights"], CONFIG["selection"]["selected"])
        self.assertEqual(len(grid), len(CONFIG["grid"]["cost"]) * len(CONFIG["grid"]["surplus"]))
        self.assertTrue(CONFIG["constraints"])
        retrieval = json.loads((ROOT / "configs" / "retrieval.json").read_text(encoding="utf-8"))
        self.assertEqual(CONFIG["candidates"]["top_k"], retrieval["candidate_count"]["selected"])
        self.assertEqual(CONFIG["candidates"]["product_text"], retrieval["product_text"]["selected"])

    def test_dev_results(self):
        r = METRICS["results"]
        self.assertEqual(r["violations_among_valid"], 0)
        self.assertEqual(r["solver_timeouts"], 0)
        a = METRICS["checker_agreement"]
        self.assertEqual(a["label_agreement"], a["scenarios"])
        self.assertEqual(a["min_cost_agreement"], a["scenarios"])
        self.assertEqual(a["suggested_budget_equals_checker_minimum"], a["budget_conflicts"])

    def test_phase_9_reads_dev_only(self):
        self.assertEqual(CONFIG["evaluated_splits"], ["dev"])
        self.assertNotIn("basket_test", (ROOT / "scripts" / "run_solver.py").read_text(encoding="utf-8"))
        self.assertNotIn("basket_test", json.dumps(CONFIG["data"]))


@unittest.skipUnless(HAS_BASKETS, "data/interim/instacart is missing (history scores; run prepare_transactions.py)")
class RebuildTests(unittest.TestCase):
    def test_solver_outputs_rebuild_identically(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_solver.py"), "--check"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
