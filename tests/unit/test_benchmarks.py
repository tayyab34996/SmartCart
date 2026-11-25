"""Phase 4: benchmark counts, grouped splits, label reproducibility, annotation integrity and lock."""

import hashlib
import json
import re
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.benchmarks.groups import split_ingredients, split_meal_families  # noqa: E402
from smartcart.benchmarks.language import (  # noqa: E402
    TextBuilder, budget_surface, to_catalog_amount, tokenize, unit_words,
)
from smartcart.nlu.spans import decode_bio_spans  # noqa: E402
from smartcart.validation.feasibility import check_feasibility  # noqa: E402

CONFIG = json.loads((ROOT / "configs" / "benchmarks.json").read_text(encoding="utf-8"))
OUT = {k: ROOT / v for k, v in CONFIG["outputs"].items()}
CATALOG = json.loads((ROOT / CONFIG["catalog"]).read_text(encoding="utf-8"))
SPLITS = ("train", "dev", "test")


def load_json(key):
    return json.loads(OUT[key].read_text(encoding="utf-8"))


class LanguageTests(unittest.TestCase):
    def test_builder_spans_align_with_tokens(self):
        b = TextBuilder()
        b.add("buy")
        q = b.add("250", "QUANTITY", "250")
        b.text += "g"
        b.spans.append({"label": "UNIT", "start": len(b.text) - 1, "end": len(b.text), "text": "g", "value": "g",
                        "attach_to": None})
        x = b.add("plain flour", "PRODUCT", "white_flour")
        b.spans[q]["attach_to"] = x
        out = b.finish()
        self.assertEqual(out["tokens"], ["Buy", "250", "g", "plain", "flour"])
        self.assertEqual(out["bio_tags"], ["O", "B-QUANTITY", "B-UNIT", "B-PRODUCT", "I-PRODUCT"])

    def test_misaligned_span_is_rejected(self):
        b = TextBuilder()
        b.add("buy flour")
        b.spans.append({"label": "PRODUCT", "start": 1, "end": 5, "text": "uy f", "value": None, "attach_to": None})
        with self.assertRaises(ValueError):
            b.finish()

    def test_unit_conversion_and_agreement(self):
        self.assertEqual(to_catalog_amount(Decimal(1), "lb"), ("g", "453.593"))  # NIST, rounded up to 0.001
        self.assertEqual(to_catalog_amount(Decimal(2), "tsp"), ("ml", "9.858"))
        self.assertEqual(to_catalog_amount(Decimal(1), "dozen"), ("piece", "12.000"))
        self.assertNotIn("kilograms", unit_words("kg", Decimal(1)))
        self.assertNotIn("kilogram", unit_words("kg", Decimal(2)))

    def test_budget_surfaces_tokenize_into_labelled_pieces(self):
        import random
        for seed in range(30):
            pieces, _ = budget_surface(random.Random(seed), 1500)
            for text, label in pieces:
                self.assertIn(label, {"BUDGET", "CURRENCY"})
                self.assertTrue(tokenize(text))

    def test_groups_are_deterministic(self):
        targets = CONFIG["recipe_split_targets"]
        self.assertEqual(split_meal_families(CATALOG["recipes"], 1, targets),
                         split_meal_families(list(reversed(CATALOG["recipes"])), 1, targets))
        ids = [i["id"] for i in CATALOG["ingredients"]]
        self.assertEqual(split_ingredients(ids, 1, 10), split_ingredients(list(reversed(ids)), 1, 10))


class NluAnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = [json.loads(line) for line in OUT["nlu"].read_text(encoding="utf-8").splitlines()]
        cls.split = load_json("nlu_split")

    def test_counts_and_grouped_split(self):
        self.assertEqual(len(self.examples), 900)
        per = {s: [e for e in self.examples if e["split"] == s] for s in SPLITS}
        self.assertEqual([len(per[s]) for s in SPLITS], [600, 150, 150])
        seeds = {s: set(self.split["seed_ids"][s]) for s in SPLITS}
        for a in SPLITS:
            for b in SPLITS:
                if a < b:
                    self.assertTrue(seeds[a].isdisjoint(seeds[b]))
                    fa = {e["family_id"] for e in per[a] if e["family_id"]}
                    fb = {e["family_id"] for e in per[b] if e["family_id"]}
                    self.assertTrue(fa.isdisjoint(fb), (a, b))
        for e in self.examples:
            self.assertIn(e["seed_id"], seeds[e["split"]])

    def test_tokens_tags_and_spans_agree(self):
        for e in self.examples:
            self.assertEqual(e["tokens"], [t for t, _, _ in tokenize(e["text"])], e["id"])
            self.assertEqual(len(e["tokens"]), len(e["bio_tags"]))
            decoded = decode_bio_spans(e["tokens"], e["bio_tags"])
            self.assertEqual([d["label"] for d in decoded], [s["label"] for s in e["spans"]], e["id"])
            for s in e["spans"]:
                self.assertEqual(e["text"][s["start"]:s["end"]], s["text"])

    def test_every_quantity_is_attached_to_an_item(self):
        for e in self.examples:
            for s in e["spans"]:
                if s["label"] in {"QUANTITY", "UNIT"}:
                    self.assertIn(e["spans"][s["attach_to"]]["label"], {"PRODUCT", "PANTRY"}, e["id"])

    def test_gold_requests_follow_the_contract(self):
        keys = {"request_id", "intent", "recipe_id", "servings", "items", "pantry", "budget_minor", "currency",
                "diet", "exclusions", "user_id", "needs_clarification", "clarification_type", "clarification_prompt"}
        kinds = {None, "missing_recipe", "missing_budget", "missing_pantry_quantity", "missing_item_quantity",
                 "ambiguous_diet", "low_confidence_intent"}
        for e in self.examples:
            g = e["gold"]
            self.assertEqual(set(g), keys, e["id"])
            self.assertIn(g["intent"], {"plan_meal", "build_grocery_list", "revise_basket", "unsupported"})
            self.assertIn(g["clarification_type"], kinds)
            self.assertEqual(g["needs_clarification"], g["clarification_type"] is not None)
            self.assertEqual(e["intent"], g["intent"])
            if g["intent"] == "revise_basket":
                self.assertIsNotNone(e["session"], e["id"])

    def test_paraphrases_share_gold_and_differ_in_text(self):
        by_seed = {}
        for e in self.examples:
            by_seed.setdefault(e["seed_id"], []).append(e)
        for seed_id, rows in by_seed.items():
            golds = [{k: v for k, v in r["gold"].items() if k != "request_id"} for r in rows]
            self.assertTrue(all(g == golds[0] for g in golds), seed_id)
            self.assertEqual(len({r["text"].lower() for r in rows}), len(rows), seed_id)

    def test_negation_and_label_policy(self):
        lactose = [e["id"] for e in self.examples if any(s["label"] == "DIET" and "lactose" in s["text"].lower()
                                                         for s in e["spans"])]
        self.assertEqual(lactose, [])  # lactose-free milk is dairy, so it never means dairy_free
        for e in self.examples:
            for s in e["spans"]:
                if s["label"] == "EXCLUSION":
                    self.assertFalse(re.match(r"(no|without)\b", s["text"].lower()), e["id"])  # cue stays outside


class BasketBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = load_json("basket_dev")["scenarios"]
        cls.test = load_json("basket_test")["scenarios"]
        cls.groups = load_json("groups")
        cls.examples = [json.loads(line) for line in OUT["nlu"].read_text(encoding="utf-8").splitlines()]

    def test_counts(self):
        for rows, split in ((self.dev, "dev"), (self.test, "test")):
            counts = {k: sum(r["label"] == k for r in rows) for k in ("feasible", "infeasible", "clarification")}
            self.assertEqual(counts, CONFIG["basket_targets"][split])
            self.assertEqual(sum(r["has_history"] for r in rows), CONFIG["history_scenarios"][split])

    def test_every_label_is_reproduced_by_the_checker(self):
        for row in self.dev + self.test:
            result = check_feasibility(row["gold_request"], CATALOG)
            self.assertEqual(result["label"], row["label"], row["scenario_id"])
            self.assertEqual(result.get("min_cost_minor"), row["checker"].get("min_cost_minor"))
            if row["resolved_request"]:
                self.assertEqual(check_feasibility(row["resolved_request"], CATALOG)["label"],
                                 row["resolved_checker"]["label"])

    def test_test_families_never_appear_in_dev_or_nlu_training(self):
        test_families = {r["family_id"] for r in self.test}
        self.assertTrue(test_families.isdisjoint({r["family_id"] for r in self.dev}))
        train = {e["family_id"] for e in self.examples if e["split"] in {"train", "dev"}}
        self.assertTrue(test_families.isdisjoint(train))
        for row in self.test:
            if row["family_id"].startswith("foodcom_"):
                self.assertEqual(self.groups["recipe_split"][row["family_id"]], "test")

    def test_scenarios_cover_the_required_cases(self):
        rows = self.test
        self.assertTrue(any(r["label"] == "feasible" and r["checker"]["min_cost_minor"] == r["gold_request"]["budget_minor"]
                            for r in rows))  # exact budget
        self.assertTrue(any(r["checker"].get("reason") == "budget_below_minimum_cost" for r in rows))
        self.assertTrue(any(r["checker"].get("reason") == "no_eligible_option" for r in rows))  # diet conflicts
        self.assertTrue(any(r["checker"].get("covered_by_pantry") for r in rows))
        self.assertTrue(any(r["gold_request"]["exclusions"] for r in rows))
        self.assertTrue(any(any(l["pack_count"] > 1 for l in r["checker"].get("basket", [])) for r in rows))
        kinds = {r["gold_request"]["clarification_type"] for r in rows if r["label"] == "clarification"}
        self.assertTrue({"missing_budget", "missing_pantry_quantity", "missing_recipe", "ambiguous_diet"} <= kinds)

    def test_history_users_come_from_the_instacart_sample(self):
        users = set(json.loads((ROOT / "data" / "splits" / "instacart_users.json").read_text(encoding="utf-8"))["user_ids"])
        for row in self.dev + self.test:
            if row["has_history"]:
                self.assertIn(row["gold_request"]["user_id"], users)
                self.assertGreaterEqual(len(row["history_shared_ingredients"]), CONFIG["history_min_shared_ingredients"])
            else:
                self.assertIsNone(row["gold_request"]["user_id"])


class RetrievalBenchmarkTests(unittest.TestCase):
    def test_counts_grouping_and_relevance(self):
        dev, test = load_json("retrieval_dev")["queries"], load_json("retrieval_test")["queries"]
        self.assertEqual((len(dev), len(test)), (50, 100))
        self.assertTrue({q["required_ingredient"] for q in dev}.isdisjoint({q["required_ingredient"] for q in test}))
        products = {p["id"]: p for p in CATALOG["products"]}
        for q in dev + test:
            expected = sorted(p["id"] for p in products.values() if p["ingredient_id"] == q["required_ingredient"]
                              and p["available"] and all(p["dietary"][d] == "allowed" for d in q["dietary_rules"]))
            self.assertEqual(q["relevant_ids"], expected, q["query"])
        self.assertTrue({"synonym", "brand", "misspelling", "near_match", "transliteration"}
                        <= {q["query_type"] for q in test})


class LockTests(unittest.TestCase):
    def test_locked_files_match_recorded_hashes(self):
        lock = (ROOT / "docs" / "benchmark_lock.md").read_text(encoding="utf-8")
        for key in CONFIG["locked_outputs"]:
            digest = hashlib.sha256(OUT[key].read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            self.assertIn(f"| `{CONFIG['outputs'][key]}` | `{digest}` | locked |", lock, key)

    @unittest.skipUnless((ROOT / CONFIG["instacart"]["baskets"]).is_file(),
                         "Instacart sample baskets not built (run scripts/prepare_transactions.py)")
    def test_benchmarks_rebuild_identically(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_benchmarks.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
