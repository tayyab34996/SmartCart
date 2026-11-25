"""Phase 3 (D2): Instacart sample, Track B split and ingredient-mapping tests."""

import csv
import hashlib
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.data.instacart import (  # noqa: E402
    match_product, normalise_name, read_mapping_rules, read_order_products, review_order, select_users,
    track_b_split, usable_orders_by_user, user_rank_key, wilson_interval,
)

CONFIG = json.loads((ROOT / "configs" / "instacart_sample.json").read_text(encoding="utf-8"))
OUT = {k: ROOT / v for k, v in CONFIG["outputs"].items()}
ARCHIVE = ROOT / CONFIG["archive"]


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class SamplingAndSplitTests(unittest.TestCase):
    def test_rank_key_is_sha256_of_seed_and_user(self):
        self.assertEqual(user_rank_key(7, 42), hashlib.sha256(b"7:42").hexdigest())

    def test_select_users_is_deterministic_and_order_independent(self):
        ids = list(range(1, 501))
        first = select_users(ids, 11, 50)
        self.assertEqual(first, select_users(list(reversed(ids)), 11, 50))
        self.assertEqual(first, sorted(first))
        self.assertEqual(len(set(first)), 50)
        self.assertNotEqual(first, select_users(ids, 12, 50))

    def test_select_users_refuses_too_few_eligible(self):
        with self.assertRaises(ValueError):
            select_users([1, 2, 3], 1, 4)

    def test_track_b_split(self):
        self.assertEqual(track_b_split([10, 11, 12, 13, 14]), {"train": [10, 11, 12], "validation": 13, "test": 14})
        with self.assertRaises(ValueError):
            track_b_split([1, 2])

    def test_usable_orders_drop_test_set_and_sort_by_order_number(self):
        orders = pd.DataFrame({"order_id": [5, 4, 3, 9], "user_id": [1, 1, 1, 2],
                               "eval_set": ["train", "prior", "test", "prior"], "order_number": [3, 1, 4, 1]})
        usable = usable_orders_by_user(orders)
        self.assertEqual(usable["order_id"].tolist(), [4, 5, 9])

    def test_order_products_are_streamed_filtered_and_deduplicated(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("op.csv", "order_id,product_id,add_to_cart_order,reordered\n"
                                       "1,10,1,0\n1,11,2,1\n2,10,1,0\n3,12,1,0\n3,12,2,1\n")
        with zipfile.ZipFile(buffer) as archive:
            frame, info = read_order_products(archive, "op.csv", {1, 3}, chunksize=2)
        self.assertEqual(sorted(map(tuple, frame.values.tolist())), [(1, 10), (1, 11), (3, 12)])
        self.assertEqual(list(frame.columns), ["order_id", "product_id"])  # cart position and reorder dropped
        self.assertEqual((info["rows_read"], info["chunks"], info["duplicate_rows_dropped"]), (5, 3, 1))


class MappingRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = read_mapping_rules(ROOT / CONFIG["mapping_rules"])
        catalog = json.loads((ROOT / CONFIG["catalog"]).read_text(encoding="utf-8"))
        cls.ingredients = {i["id"] for i in catalog["ingredients"]}

    def test_rules_name_catalog_ingredients(self):
        self.assertTrue({r["ingredient_id"] for r in self.rules} <= self.ingredients)

    def test_normalise_name(self):
        self.assertEqual(normalise_name("  Diced Tomatoes &  Green Chilies "), "diced tomatoes and green chilies")

    def test_specific_rules_win_over_general_ones(self):
        cases = [("Green Onions", 83, "green_onion"), ("Organic Yellow Onion", 83, "onion"),
                 ("Garlic Powder", 104, "garlic_powder"), ("Organic Garlic", 83, "garlic"),
                 ("Light Brown Sugar", 17, "brown_sugar"), ("Cane Sugar", 17, "sugar"),
                 ("Original Diced Tomatoes & Green Chilies", 81, "diced_tomatoes_green_chilies"),
                 ("Organic Diced Tomatoes", 81, "canned_diced_tomatoes"),
                 ("Chicken Breast Cutlets", 49, "chicken_cutlet"),
                 ("Boneless Skinless Chicken Breasts", 49, "chicken_breast")]
        for name, aisle, expected in cases:
            winner, _ = match_product(name, aisle, self.rules)
            self.assertEqual(winner and winner["ingredient_id"], expected, name)

    def test_aisle_and_exclusions_block_near_misses(self):
        for name, aisle in [("Garlic Bread", 112), ("Peanut Butter Cups", 45), ("Chocolate Milk", 84),
                            ("Sparkling Water Lemon", 115), ("Peanut Butter", 72), ("Onion Rings", 129),
                            ("Smoked Paprika", 104), ("Coconut Milk Beverage", 91)]:
            winner, _ = match_product(name, aisle, self.rules)
            self.assertIsNone(winner, name)
        winner, _ = match_product("Creamy Peanut Butter", 88, self.rules)
        self.assertEqual(winner["ingredient_id"], "peanut_butter")

    def test_review_order_and_wilson_interval(self):
        self.assertEqual(review_order([3, 1, 2], "s"), review_order([2, 3, 1], "s"))
        low, high = wilson_interval(134, 150)
        self.assertAlmostEqual(low, 0.8338, places=3)
        self.assertAlmostEqual(high, 0.9333, places=3)
        with self.assertRaises(ValueError):
            wilson_interval(0, 0)


class CommittedOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.users = json.loads(OUT["users"].read_text(encoding="utf-8"))
        cls.trackb = json.loads(OUT["trackb"].read_text(encoding="utf-8"))
        cls.mapping = read_csv(OUT["mapping"])
        cls.checks = json.loads(OUT["checks"].read_text(encoding="utf-8"))

    def test_user_manifest(self):
        ids = self.users["user_ids"]
        self.assertEqual(len(ids), CONFIG["n_users"])
        self.assertEqual(ids, sorted(set(ids)))
        self.assertEqual(self.users["seed"], CONFIG["seed"])
        digest = hashlib.sha256(",".join(map(str, ids)).encode("ascii")).hexdigest()
        self.assertEqual(digest, self.users["user_ids_sha256"])

    def test_trackb_manifest_covers_sample_without_overlap(self):
        splits = self.trackb["users"]
        self.assertEqual(sorted(int(u) for u in splits), self.users["user_ids"])
        seen = set()
        for split in splits.values():
            orders = split["train"] + [split["validation"], split["test"]]
            self.assertGreaterEqual(len(split["train"]), CONFIG["min_usable_orders"] - 2)
            self.assertTrue(seen.isdisjoint(orders))
            seen.update(orders)

    def test_mapping_covers_every_recipe_ingredient(self):
        catalog = json.loads((ROOT / CONFIG["catalog"]).read_text(encoding="utf-8"))
        used = {line["ingredient_id"] for r in catalog["recipes"] for line in r["ingredients"]}
        mapped = {m["ingredient_id"] for m in self.mapping}
        self.assertTrue(used <= mapped)
        ids = [int(m["instacart_product_id"]) for m in self.mapping]
        self.assertEqual(ids, sorted(set(ids)))

    def test_checks_pass_and_review_matches_mapping(self):
        self.assertTrue(self.checks["all_checks_pass"])
        review = self.checks["mapping"]["manual_review"]
        self.assertTrue(review["review_matches_current_mapping"])
        rows = read_csv(ROOT / CONFIG["mapping_review"])
        self.assertEqual(review["precision_correct"],
                         sum(r["judgement"] == "correct" for r in rows if r["review_set"] == "precision_heldout"))
        self.assertTrue(all(r["note"] for r in rows if r["judgement"] in {"incorrect", "missed"}))

    @unittest.skipUnless(ARCHIVE.is_file(), "raw Instacart archive not present")
    def test_manifests_rebuild_from_archive(self):
        import subprocess
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "prepare_transactions.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
