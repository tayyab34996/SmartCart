"""Phase 8: ingredient-level rules from training orders only, the bounded pair score, the
history score, Track B rankers and metrics, the selection-activity measurement and the
rebuild checks. Tests that need the Instacart working files skip on a clone without
``data/interim/instacart/`` (rebuild them with ``scripts/prepare_transactions.py``)."""

import csv
import json
import re
import subprocess
import sys
import unittest
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.associations import api  # noqa: E402
from smartcart.associations.activity import measure  # noqa: E402
from smartcart.associations.mining import (  # noqa: E402
    filter_rules, lift_to_score, mine_itemsets, mine_rules, one_hot, pair_matrix, pair_table,
)
from smartcart.associations.trackb import (  # noqa: E402
    Users, association_term, paired_bootstrap, scores, top_k, user_half, user_metrics,
)
from smartcart.associations.transactions import load_manifest, load_trackb  # noqa: E402

CONFIG = json.loads((ROOT / "configs" / "associations.json").read_text(encoding="utf-8"))
DATA = CONFIG["data"]
CATALOG = json.loads((ROOT / DATA["catalog"]).read_text(encoding="utf-8"))
HAS_BASKETS = (ROOT / DATA["baskets"]).is_file()
NEEDS_BASKETS = unittest.skipUnless(HAS_BASKETS, "data/interim/instacart is missing (run prepare_transactions.py)")
RULES = list(csv.DictReader((ROOT / CONFIG["outputs"]["rules"]).open(encoding="utf-8", newline="")))
TRACKB_METRICS = json.loads((ROOT / CONFIG["outputs"]["trackb_metrics"]).read_text(encoding="utf-8"))
ACTIVITY = json.loads((ROOT / CONFIG["outputs"]["selection_activity"]).read_text(encoding="utf-8"))
SELECTED = CONFIG["selection"]["selected"]


def run_script(name, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / name), *args], cwd=ROOT,
                          capture_output=True, text=True)


class MiningTests(unittest.TestCase):
    BASKETS = [frozenset(b) for b in (["a", "b"], ["a", "b", "c"], ["a", "c"], ["b"], [], ["a", "b"])]
    ITEMS = ["a", "b", "c", "d"]

    def test_counts_match_brute_force(self):
        frame = one_hot(self.BASKETS, self.ITEMS)
        itemsets = mine_itemsets(frame, 1, 3)
        for itemset, count in zip(itemsets["itemsets"], itemsets["count"]):
            self.assertEqual(count, sum(itemset <= b for b in self.BASKETS))
        self.assertNotIn(frozenset(["d"]), set(itemsets["itemsets"]))  # never bought

    def test_pair_table_and_scores(self):
        frame = one_hot(self.BASKETS, self.ITEMS)
        rules = mine_rules(mine_itemsets(frame, 1, 2), len(frame))
        pairs = pair_table(rules)
        ab = pairs[("a", "b")]
        self.assertEqual(ab["count"], 3)
        self.assertAlmostEqual(ab["confidence_ab"], 3 / 4)  # a -> b
        self.assertAlmostEqual(ab["confidence_ba"], 3 / 4)  # b -> a
        self.assertAlmostEqual(ab["lift"], (3 / 6) / ((4 / 6) * (4 / 6)), places=5)
        matrix = pair_matrix(pairs, self.ITEMS, 1, 0.0)
        self.assertTrue(np.array_equal(matrix, matrix.T))
        self.assertTrue(np.all(np.diag(matrix) == 0))
        self.assertTrue(np.all((matrix >= 0) & (matrix <= 1)))
        self.assertEqual(pair_matrix(pairs, self.ITEMS, 4, 0.0).sum(), 0.0)  # count threshold
        strict = pair_matrix(pairs, self.ITEMS, 1, 0.9)  # only c -> a has confidence >= 0.9 (2 of 2)
        self.assertGreater(strict[0, 2], 0.0)
        self.assertEqual(strict[0, 1], 0.0)

    def test_lift_transform_is_bounded(self):
        self.assertEqual(lift_to_score(1.0), 0.0)
        self.assertEqual(lift_to_score(0.5), 0.0)
        self.assertAlmostEqual(lift_to_score(4.0), 0.75)
        self.assertLessEqual(lift_to_score(1e9), 1.0)
        self.assertLess(lift_to_score(100.0), 1.0)

    def test_filter_keeps_both_directions_of_a_passing_pair(self):
        frame = one_hot(self.BASKETS, self.ITEMS)
        rules = mine_rules(mine_itemsets(frame, 1, 3), len(frame))
        kept = filter_rules(rules, 3, 0.0)
        pairs = {(r["antecedent"], r["consequent"]) for r in kept if r["length"] == 2}
        self.assertEqual(pairs, {("a", "b"), ("b", "a")})


class TrainingOnlyTests(unittest.TestCase):
    def test_manifest_loads_only_the_requested_splits(self):
        users = load_manifest(ROOT / DATA["trackb"], ("train",))
        self.assertTrue(all(set(r) == {"train"} for r in users.values()))
        with self.assertRaises(ValueError):
            load_manifest(ROOT / DATA["trackb"], ("holdout",))

    def test_phase_8_never_reads_test_orders(self):
        self.assertNotIn("test", json.dumps(CONFIG["evaluated_splits"]).replace("test_split", ""))
        for script in ("mine_rules.py", "evaluate_trackb.py"):
            text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
            for splits in re.findall(r"splits=\(([^)]*)\)", text):
                self.assertNotIn("test", splits)
            self.assertNotIn('split_orders("test")', text)
            self.assertNotIn('["test"]', text)

    @NEEDS_BASKETS
    def test_rule_counts_come_from_training_orders_only(self):
        trackb = load_trackb(CATALOG, ROOT / DATA["trackb"], ROOT / DATA["mapping"], ROOT / DATA["baskets"],
                             splits=("train", "validation"))
        train = [trackb.orders[o] for o in trackb.split_orders("train")]
        both = train + [trackb.orders[o] for o in trackb.split_orders("validation")]

        def count(baskets, a, b):
            return sum(a in x and b in x for x in baskets)

        pair_rows = [r for r in RULES if int(r["length"]) == 2]
        self.assertTrue(pair_rows)
        differs = 0
        for r in pair_rows:
            self.assertEqual(int(r["count"]), count(train, r["antecedent"], r["consequent"]))
            differs += count(both, r["antecedent"], r["consequent"]) != int(r["count"])
        self.assertGreater(differs, 0)  # the test would notice validation orders leaking in
        summary = json.loads((ROOT / CONFIG["outputs"]["rules_summary"]).read_text(encoding="utf-8"))
        self.assertEqual(summary["transactions"], len(train))


class ApiTests(unittest.TestCase):
    def test_pair_score_contract(self):
        ingredients = [i["id"] for i in CATALOG["ingredients"]]
        for a, b in combinations(ingredients[:40], 2):
            s = api.pair_score(a, b)
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)
            self.assertEqual(s, api.pair_score(b, a))
        self.assertEqual(api.pair_score("garlic", "garlic"), 0.0)
        self.assertEqual(api.pair_score("garlic", "not_an_item"), 0.0)

    def test_pair_score_matches_rules_and_products_use_their_ingredient(self):
        row = next(r for r in RULES if int(r["length"]) == 2 and float(r["lift"]) > 1)
        a, b = row["antecedent"], row["consequent"]
        self.assertEqual(api.pair_score(a, b), lift_to_score(float(row["lift"])))
        pa = next(p["id"] for p in CATALOG["products"] if p["ingredient_id"] == a)
        pb = next(p["id"] for p in CATALOG["products"] if p["ingredient_id"] == b)
        self.assertEqual(api.pair_score(pa, pb), api.pair_score(a, b))
        same = [p["id"] for p in CATALOG["products"] if p["ingredient_id"] == a][:2]
        if len(same) == 2:
            self.assertEqual(api.pair_score(*same), 0.0)

    def test_basket_pair_score_is_a_bounded_mean(self):
        items = ["garlic", "onion", "cilantro", "lime"]
        pairs = [api.pair_score(a, b) for a, b in combinations(items, 2)]
        self.assertAlmostEqual(api.basket_pair_score(items), sum(pairs) / len(pairs))
        self.assertEqual(api.basket_pair_score(["garlic"]), 0.0)
        self.assertLessEqual(api.basket_pair_score(items * 5), 1.0)

    def test_rules_use_the_frozen_thresholds(self):
        self.assertTrue(all(int(r["count"]) >= SELECTED["min_count"] for r in RULES))
        self.assertEqual({r["length"] for r in RULES} - {"2", "3"}, set())

    @NEEDS_BASKETS
    def test_history_score(self):
        uid = int(next(iter(api._history())))
        values = [api.history_score(uid, i["id"]) for i in CATALOG["ingredients"]]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in values))
        self.assertGreater(max(values), 0.0)
        self.assertEqual(api.history_score(-1, "milk"), 0.0)
        self.assertEqual(api.history_score(None, "milk"), 0.0)
        self.assertEqual(api.history_score(uid, "not_an_item"), 0.0)
        product = next(p["id"] for p in CATALOG["products"] if p["ingredient_id"] == "milk")
        self.assertEqual(api.history_score(uid, product), api.history_score(uid, "milk"))


class TrackBTests(unittest.TestCase):
    def test_metrics(self):
        m = user_metrics([0, 5, 1, 7], {1, 2}, 10)
        self.assertAlmostEqual(m["recall"], 0.5)
        self.assertAlmostEqual(m["ndcg"], (1 / np.log2(4)) / (1 + 1 / np.log2(3)))
        self.assertEqual(user_metrics([3, 4], {3}, 10)["ndcg"], 1.0)

    def test_ties_go_to_popularity_then_item(self):
        score = np.array([[0.0, 0.5, 0.0, 0.0]])
        pop = np.array([1.0, 0.0, 3.0, 1.0])
        self.assertEqual(top_k(score, pop, 4).tolist(), [[1, 2, 0, 3]])

    def test_association_term(self):
        freq = np.array([[0.5, 0.5, 0.0]])
        pairs = np.array([[0, 0.4, 0.8], [0.4, 0, 0.0], [0.8, 0.0, 0]])
        term = association_term(freq, pairs)
        self.assertTrue(np.allclose(term, [[0.4, 0.4, 0.4]]))  # item 2: (0.5*0.8 + 0.5*0) / 1.0
        self.assertTrue(np.allclose(association_term(np.zeros((1, 3)), pairs), 0.0))
        users = Users([1], freq, [{2}])
        self.assertTrue(np.allclose(scores("association", users, pairs, 0.5), freq + 0.5 * term))
        self.assertTrue(np.allclose(scores("popularity", users), 0.0))

    def test_user_halves_are_deterministic_and_balanced(self):
        seed = CONFIG["trackb"]["user_split"]["seed"]
        halves = [user_half(u, seed) for u in range(1, 2001)]
        self.assertEqual(halves, [user_half(u, seed) for u in range(1, 2001)])
        self.assertLess(abs(halves.count("tune") - 1000), 100)
        u = TRACKB_METRICS["users"]
        self.assertEqual(u["tune"] + u["report"], u["evaluated"])
        self.assertEqual(u["evaluated"] + u["excluded_empty_target"], u["sampled"])

    def test_paired_bootstrap(self):
        a, b = [1.0, 0.0, 1.0, 1.0], [0.0, 0.0, 1.0, 0.0]
        out = paired_bootstrap(a, b, 200, 1)
        self.assertEqual(out, paired_bootstrap(a, b, 200, 1))
        self.assertAlmostEqual(out["mean_difference"], 0.5)
        self.assertLessEqual(out["ci95"][0], 0.5)
        self.assertGreaterEqual(out["ci95"][1], 0.5)

    def test_frozen_choice_follows_the_rule(self):
        grid = TRACKB_METRICS["selection"]["grid"]
        best = min(grid, key=lambda r: (-r["ndcg_at_10"], -r["recall_at_10"], -r["min_count"],
                                        -r["min_confidence"], r["weight"]))
        self.assertEqual({k: best[k] for k in ("min_count", "min_confidence", "weight")}, SELECTED)
        g = CONFIG["grid"]
        self.assertEqual(len(grid), len(g["min_count"]) * len(g["min_confidence"]) * len(g["weight"]))

    def test_rankers_share_users_and_universe(self):
        for half in ("tune", "report", "all_validation"):
            rankers = ("popularity", "frequency", "association")
            counts = {r: TRACKB_METRICS["results"][half][r]["num_users"] for r in rankers}
            self.assertEqual(len(set(counts.values())), 1)


class ActivityTests(unittest.TestCase):
    def test_brand_level_scores_would_be_detected(self):
        scenarios = json.loads((ROOT / DATA["basket_dev"]).read_text(encoding="utf-8"))["scenarios"]

        def varying_pair(a, b):
            return 0.9 if a.startswith("sel_") and b.startswith("sel_") else 0.1

        out = measure(scenarios, CATALOG, varying_pair, lambda u, x: 0.0)
        self.assertGreater(out["pair_term_varies_with_choice"], 0)

    def test_association_terms_do_not_change_selection(self):
        self.assertEqual(ACTIVITY["pair_term_varies_with_choice"], 0)
        self.assertEqual(ACTIVITY["history_term_varies_with_choice"], 0)
        self.assertGreater(ACTIVITY["pair_term_nonzero"], 0)  # the term is active, just constant
        scenarios = json.loads((ROOT / DATA["basket_dev"]).read_text(encoding="utf-8"))["scenarios"]
        out = measure(scenarios, CATALOG, api.pair_score, lambda u, x: 0.0)
        self.assertEqual(out["pair_term_varies_with_choice"], 0)
        self.assertEqual(out["pair_term_nonzero"], ACTIVITY["pair_term_nonzero"])


@NEEDS_BASKETS
class RebuildTests(unittest.TestCase):
    def test_rules_rebuild_identically(self):
        result = run_script("mine_rules.py", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_trackb_metrics_rebuild_identically(self):
        result = run_script("evaluate_trackb.py", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
