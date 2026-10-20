"""Small adversarial fixtures for data-audit correctness."""

import csv
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from smartcart.data.audit import (
    audit_foodcom,
    audit_instacart,
    csv_rows,
    parse_r_vector,
    positive_amount,
    positive_number,
)


def make_archive(path, tables):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, (columns, rows) in tables.items():
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(columns)
            writer.writerows(rows)
            archive.writestr(name, buffer.getvalue())


class RecipeParsingTests(unittest.TestCase):
    def test_commas_missing_markers_and_escaped_quotes_preserve_alignment(self):
        self.assertEqual(
            parse_r_vector(r'c("lemon, zest of", NA, "a \"quoted\" ingredient")'),
            ["lemon, zest of", None, r'a \"quoted\" ingredient'],
        )
        self.assertEqual(parse_r_vector('"rice"'), ["rice"])
        self.assertEqual(parse_r_vector("NA"), [])
        self.assertEqual(parse_r_vector("c()"), [])
        self.assertEqual(parse_r_vector("character(0)"), [])
        self.assertEqual(parse_r_vector("numeric(0)"), [])

    def test_executable_or_malformed_text_is_rejected(self):
        for text in ('c("rice", system("touch bad"))', '__import__("os")',
                     'c("rice",)', 'c("rice" "milk")'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_r_vector(text)

    def test_ambiguous_missing_and_nonpositive_amounts_are_rejected(self):
        for value in ("1/4", "1 1/2", "0.5", "2"):
            self.assertTrue(positive_amount(value), value)
        for value in (None, "", "NA", "to taste", "1-2", "1/0", "0", "-1", "NaN", "1 2", "1/2 1/4"):
            self.assertFalse(positive_amount(value), value)
        for value in ("NA", "", "0", "-1", "NaN", "inf"):
            self.assertFalse(positive_number(value), value)

    def test_foodcom_structural_acceptance_never_implies_unit_verification(self):
        columns = ["RecipeId", "Name", "RecipeCategory", "RecipeIngredientParts",
                   "RecipeIngredientQuantities", "RecipeServings"]
        ingredients = 'c("rice", "milk", "sugar", "salt")'
        rows = [
            [1, "Rice meal", "Rice", ingredients, 'c("1", "2", "1/2", "1")', "4"],
            [2, "Mismatched rice", "Rice", ingredients, 'c("1", "2")', "4"],
            [3, "Missing amount", "Rice", ingredients, 'c("1", "2", NA, "1")', "4"],
            [4, "Missing servings", "Rice", ingredients, 'c("1", "2", "1", "1")', "NA"],
            [5, "Unsafe syntax", "Rice", 'system("bad")', 'c("1")', "4"],
            [1, "Rice meal", "Rice", ingredients, 'c("1", "2", "1/2", "1")', "4"],
            [6, "No ingredients", "Rice", "character(0)", "character(0)", "4"],
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "recipes.zip"
            make_archive(path, {"recipes.csv": (columns, rows)})
            summary, candidates = audit_foodcom(path)
        self.assertEqual(summary["rows"], 7)
        self.assertEqual(summary["duplicate_ids"], 1)
        self.assertEqual(summary["empty_ingredient_lists"], 1)
        self.assertEqual(summary["ingredient_quantity_length_mismatches"], 1)
        self.assertEqual(summary["missing_or_invalid_servings"], 1)
        self.assertEqual(summary["unsupported_vector_syntax_rows"], 1)
        self.assertEqual(summary["structurally_usable_before_unit_review"], 2)
        self.assertEqual(len(candidates), 1)
        self.assertFalse(candidates[0]["optimizer_ready"])
        self.assertEqual(candidates[0]["unit_review_status"], "unverified")


class TransactionAuditTests(unittest.TestCase):
    def test_broken_links_duplicate_items_and_missing_baskets_are_visible(self):
        tables = {
            "aisles.csv": (["aisle_id", "aisle"], [[1, "rice"]]),
            "departments.csv": (["department_id", "department"], [[1, "food"]]),
            "products.csv": (["product_id", "product_name", "aisle_id", "department_id"],
                             [[1, "Rice", 1, 1], [2, "Milk", 1, 1]]),
            "orders.csv": (["order_id", "user_id", "eval_set", "order_number", "order_dow",
                            "order_hour_of_day", "days_since_prior_order"],
                           [[1, 1, "prior", 1, 1, 10, ""],
                            [2, 1, "train", 2, 1, 10, 7],
                            [3, 2, "prior", 1, 1, 10, ""],
                            [4, 3, "prior", 1, 1, 10, ""]]),
            "order_products__prior.csv": (
                ["order_id", "product_id", "add_to_cart_order", "reordered"],
                [[1, 1, 1, 0], [1, 1, 1, 0], [3, 2, 1, 0], [1, 2, 3, 0], [99, 99, 0, 2]]),
            "order_products__train.csv": (
                ["order_id", "product_id", "add_to_cart_order", "reordered"], [[2, 2, 1, 1]]),
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "instacart.zip"
            make_archive(path, tables)
            summary = audit_instacart(path)
        prior = summary["order_products"]["prior"]
        self.assertEqual(prior["unknown_product_ids"], 1)
        self.assertEqual(prior["unknown_order_ids"], 1)
        self.assertEqual(prior["fragmented_order_groups"], 1)
        self.assertEqual(prior["duplicate_products_within_contiguous_order_group"], 1)
        self.assertEqual(prior["orders_missing_product_rows"], 1)
        self.assertEqual(prior["invalid_reordered_flags"], 1)
        self.assertFalse(prior["global_pair_duplicate_check_complete"])
        self.assertEqual(summary["orders"]["missing_gap_after_first_order"], 0)

    def test_missing_columns_and_truncated_records_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            make_archive(path, {"missing.csv": (["a"], [[1]]),
                                "truncated.csv": (["a", "b"], [[1]])})
            with zipfile.ZipFile(path) as archive:
                with self.assertRaises(ValueError):
                    with csv_rows(archive, "missing.csv", {"a", "b"}):
                        pass
                with self.assertRaises(ValueError):
                    with csv_rows(archive, "truncated.csv", {"a", "b"}) as (_, rows):
                        list(rows)


if __name__ == "__main__":
    unittest.main()
