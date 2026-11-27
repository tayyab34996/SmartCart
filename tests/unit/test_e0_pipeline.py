"""Phase 5: TF-IDF retrieval API, E0 selection with post-hoc filtering, and the basket validator."""

import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.pipeline.e0 import select_e0_basket  # noqa: E402
from smartcart.retrieval.api import retrieve_candidates  # noqa: E402
from smartcart.validation.feasibility import check_feasibility  # noqa: E402
from smartcart.validation.validator import validate_basket  # noqa: E402

CONFIG = json.loads((ROOT / "configs" / "experiments" / "E0.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / CONFIG["data"]["catalog"]).read_text(encoding="utf-8"))
DEV = json.loads((ROOT / CONFIG["data"]["basket_dev"]).read_text(encoding="utf-8"))["scenarios"]
PRODUCTS = {p["id"]: p for p in CATALOG["products"]}


def request(**fields):
    base = {"request_id": "t", "intent": "plan_meal", "recipe_id": "foodcom_3474", "servings": 4, "items": [],
            "pantry": {}, "budget_minor": None, "currency": "PKR", "diet": [], "exclusions": [], "user_id": None,
            "needs_clarification": False, "clarification_type": None, "clarification_prompt": None}
    return {**base, **fields}


class RetrievalApiTests(unittest.TestCase):
    def test_ranks_the_whole_catalog_with_bounded_scores(self):
        ranked = retrieve_candidates("cheddar", CATALOG, top_k=10)
        self.assertEqual([r["rank"] for r in ranked], list(range(1, 11)))
        self.assertTrue(all(0.0 <= r["retrieval_score"] <= 1.0 for r in ranked))
        self.assertEqual(ranked, retrieve_candidates("cheddar", CATALOG, top_k=10))
        self.assertEqual(len(retrieve_candidates("cheddar", CATALOG, top_k=len(PRODUCTS))), len(PRODUCTS))

    def test_retrieval_does_not_enforce_hard_rules(self):
        ranked = retrieve_candidates("cheddar", CATALOG, top_k=10)
        self.assertTrue(any(PRODUCTS[r["product_id"]]["ingredient_id"] != "cheddar" for r in ranked))

    def test_e0_keeps_the_phase_1_product_text(self):
        # Phase 7 changed the default product text; E0 pins "legacy" so its results reproduce.
        import inspect

        self.assertEqual(inspect.signature(select_e0_basket).parameters["product_text"].default, "legacy")
        self.assertNotEqual(retrieve_candidates("dill_weed", CATALOG, top_k=10, product_text="legacy"),
                            retrieve_candidates("dill_weed", CATALOG, top_k=10))


class SelectionTests(unittest.TestCase):
    def test_matches_checker_minimum_when_no_diet_applies(self):
        # Line costs add up and each line takes one product, so the cheapest product per line is the
        # minimum-cost basket whenever the pool holds it and no diet filter removes anything.
        for s in DEV:
            gold = s["gold_request"]
            if s["label"] != "feasible" or gold["diet"]:
                continue
            basket = select_e0_basket(gold, CATALOG, top_k=10)
            self.assertEqual(basket["status"], "valid", s["scenario_id"])
            self.assertEqual(basket["total_cost_minor"], s["checker"]["min_cost_minor"], s["scenario_id"])

    def test_post_hoc_diet_filter_leaves_lines_uncovered(self):
        basket = select_e0_basket(request(diet=["vegan"]), CATALOG, top_k=10)
        self.assertEqual(basket["status"], "incomplete")
        removed = [x for x in basket["lines"] if x["line_status"] == "removed_by_diet_filter"]
        self.assertTrue(removed)
        self.assertTrue(all(PRODUCTS[x["removed_product_id"]]["dietary"]["vegan"] != "allowed" for x in removed))

    def test_over_budget_and_no_requirements(self):
        self.assertEqual(select_e0_basket(request(budget_minor=100), CATALOG)["status"], "over_budget")
        self.assertEqual(select_e0_basket(request(recipe_id=None), CATALOG)["status"], "no_requirements")
        self.assertEqual(select_e0_basket(request(recipe_id="foodcom_0"), CATALOG)["status"], "invalid_request")

    def test_small_pool_can_miss_compatible_products(self):
        basket = select_e0_basket(request(), CATALOG, top_k=1)
        self.assertTrue(all(x["compatible_in_pool"] <= 1 for x in basket["lines"]))

    def test_reference_requests_match_hand_calculation(self):
        reference = json.loads((ROOT / CONFIG["outputs"]["reference_baskets"]).read_text(encoding="utf-8"))
        self.assertEqual(len(reference["scenarios"]), 5)
        self.assertTrue(reference["all_match"])
        self.assertTrue(all(s["purchased"] or s["covered_by_pantry"] for s in reference["scenarios"]))


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.scenario = next(s for s in DEV if s["label"] == "feasible" and s["gold_request"]["budget_minor"])
        self.gold = self.scenario["gold_request"]
        self.lines = deepcopy(self.scenario["checker"]["basket"])

    def kinds(self, lines, req=None):
        return {v["type"] for v in validate_basket(req or self.gold, lines, CATALOG)["violations"]}

    def test_checker_basket_is_valid(self):
        result = validate_basket(self.gold, self.lines, CATALOG)
        self.assertTrue(result["valid"], result["violations"])
        self.assertEqual((result["coverage"], result["total_cost_minor"]), (1.0, self.scenario["checker"]["min_cost_minor"]))

    def test_rejects_corrupted_baskets(self):
        self.assertIn("missing_ingredient", self.kinds(self.lines[1:]))
        self.assertIn("duplicate_line", self.kinds(self.lines + [self.lines[0]]))
        short = deepcopy(self.lines)
        need = next(x for x in check_feasibility(self.gold, CATALOG)["resolved"]["lines"]
                    if x["ingredient_id"] == short[0]["ingredient_id"])
        if float(need["need"]) > 0:
            short[0]["pack_count"] = 0
            self.assertIn("invalid_pack_count", self.kinds(short))
        wrong = deepcopy(self.lines)
        wrong[0]["line_cost_minor"] += 1
        self.assertIn("line_cost_mismatch", self.kinds(wrong))
        other = next(p for p in CATALOG["products"]
                     if p["ingredient_id"] not in {x["ingredient_id"] for x in self.lines} and p["available"])
        self.assertIn("unrequested_ingredient", self.kinds(self.lines + [{"product_id": other["id"], "pack_count": 1}]))
        self.assertIn("over_budget", self.kinds(self.lines, {**self.gold, "budget_minor": 1}))
        self.assertIn("unknown_product", self.kinds(self.lines + [{"product_id": "nope", "pack_count": 1}]))

    def test_rejects_diet_exclusion_and_quantity_violations(self):
        product = next(PRODUCTS[x["product_id"]] for x in self.lines
                       if any(v != "allowed" for v in PRODUCTS[x["product_id"]]["dietary"].values()))
        diet = next(d for d, v in product["dietary"].items() if v != "allowed")
        self.assertIn("diet_violation", self.kinds(self.lines, {**self.gold, "diet": [diet]}))
        excluded = {**self.gold, "exclusions": [product["ingredient_id"]]}
        self.assertIn("excluded_ingredient", self.kinds(self.lines, excluded))
        big = {**self.gold, "servings": (self.gold["servings"] or 4) * 20}
        self.assertIn("insufficient_quantity", self.kinds(self.lines, big))


class RunTests(unittest.TestCase):
    def test_committed_runs_cover_dev_only(self):
        dev_ids = {s["scenario_id"] for s in DEV}
        for mode in ("gold_input", "end_to_end"):
            path = ROOT / CONFIG["outputs"]["basket_predictions"].format(mode=mode)
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({r["scenario_id"] for r in rows}, dev_ids)
            for r in rows:  # every basket labelled valid was checked by the validator
                if r["status"] == "valid":
                    self.assertIsNotNone(r["score"]["validator"])

    def test_baseline_outputs_rebuild_identically(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_baseline.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
