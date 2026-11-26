"""Phase 5: E0 baseline parser (TF-IDF + LinearSVC intent, rule/dictionary slots)."""

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.benchmarks.language import tokenize  # noqa: E402
from smartcart.nlu.api import build_baseline_parser, parse_request, split_rows  # noqa: E402
from smartcart.nlu.lexicon import parse_number  # noqa: E402
from smartcart.nlu.metrics import attachment_accuracy, slot_metrics  # noqa: E402

CONFIG = json.loads((ROOT / "configs" / "experiments" / "E0.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / CONFIG["data"]["catalog"]).read_text(encoding="utf-8"))
PARSER = build_baseline_parser(CATALOG, CONFIG, ROOT)
SESSION = {"request_id": "s0", "intent": "plan_meal", "recipe_id": "foodcom_3474", "servings": 4, "items": [],
           "pantry": {}, "budget_minor": 150000, "currency": "PKR", "diet": [], "exclusions": [], "user_id": None,
           "needs_clarification": False, "clarification_type": None, "clarification_prompt": None}


def spans_of(text, intent="build_grocery_list"):
    return [(s["label"], s["text"], s["value"]) for s in PARSER.slots.extract(text, intent)]


class NumberTests(unittest.TestCase):
    def number(self, text):
        value, end, suffix = parse_number(tokenize(text), 0)
        return value, suffix

    def test_digit_forms(self):
        self.assertEqual(self.number("1,350"), (Decimal(1350), False))
        self.assertEqual(self.number("1.5k"), (Decimal(1500), True))
        self.assertEqual(self.number("3550/-"), (Decimal(3550), True))

    def test_word_forms(self):
        self.assertEqual(self.number("twenty-five hundred")[0], 2500)
        self.assertEqual(self.number("two thousand")[0], 2000)
        self.assertEqual(self.number("twelve")[0], 12)
        self.assertEqual(self.number("a dozen")[0], 1)
        self.assertIsNone(parse_number(tokenize("a bit"), 0))


class SlotTests(unittest.TestCase):
    def test_quantities_units_and_attachment(self):
        request = PARSER.parse("Buy 2 litres of milk, 500g parmesan and four red potatoes")
        self.assertEqual(request["items"], [
            {"ingredient_id": "milk", "amount": "2000.000", "unit": "ml"},
            {"ingredient_id": "parmesan", "amount": "500.000", "unit": "g"},
            {"ingredient_id": "potato", "amount": "4.000", "unit": "piece"}])
        spans = PARSER.slots.extract("Buy 2 litres of milk", "build_grocery_list")
        product = next(i for i, s in enumerate(spans) if s["label"] == "PRODUCT")
        self.assertTrue(all(s["attach_to"] == product for s in spans if s["label"] in {"QUANTITY", "UNIT"}))

    def test_dozen_and_pounds(self):
        request = PARSER.parse("I need a dozen eggs and one pound sour cream")
        self.assertEqual([(i["ingredient_id"], i["amount"]) for i in request["items"]],
                         [("egg", "12.000"), ("sour_cream", "453.593")])

    def test_negated_diet_category_is_a_diet_span(self):
        self.assertIn(("DIET", "no dairy", "dairy_free"), spans_of("Make lime rice, no dairy", "plan_meal"))
        self.assertIn(("DIET", "nut-free", "nut_free"), spans_of("Make it nut-free", "plan_meal"))

    def test_negated_ingredient_is_an_exclusion_on_the_ingredient_only(self):
        spans = spans_of("Make homemade pasta and skip the olive oil", "plan_meal")
        self.assertIn(("EXCLUSION", "olive oil", "olive_oil"), spans)
        self.assertEqual(PARSER.parse("Make homemade pasta without olive oil")["exclusions"], ["olive_oil"])

    def test_pantry_with_and_without_amount(self):
        request = PARSER.parse("Make homemade pasta for 2, I have 200 g plain flour at home")
        self.assertEqual(request["pantry"], {"white_flour": "200.000"})
        self.assertFalse(request["needs_clarification"])
        request = PARSER.parse("Make homemade pasta, there's a bit of plain flour in my pantry")
        self.assertEqual(request["pantry"], {"white_flour": None})
        self.assertEqual(request["clarification_type"], "missing_pantry_quantity")

    def test_budget_and_currency_forms(self):
        spans = spans_of("Make homemade pasta, under Rs. 2,600/- for six", "plan_meal")
        self.assertIn(("CURRENCY", "Rs.", "PKR"), spans)
        self.assertIn(("BUDGET", "2,600/-", 2600), spans)
        self.assertIn(("SERVINGS", "six", 6), spans)
        self.assertEqual(PARSER.parse("Make homemade pasta, budget 5k")["budget_minor"], 500000)

    def test_ingredient_alias_beats_ambiguous_diet_word(self):
        self.assertIn(("PRODUCT", "light olive oil", "olive_oil"), spans_of("Buy 500 ml light olive oil"))
        self.assertEqual(PARSER.parse("Make homemade pasta, keep it keto")["clarification_type"], "ambiguous_diet")

    def test_clarification_rules(self):
        self.assertEqual(PARSER.parse("I want to make lasagna for 4")["clarification_type"], "missing_recipe")
        self.assertEqual(PARSER.parse("Make homemade pasta, keep it cheap")["clarification_type"], "missing_budget")
        self.assertEqual(PARSER.parse("Buy milk and 2 kg plain flour")["clarification_type"], "missing_item_quantity")
        self.assertEqual(PARSER.parse("Can you tell me the weather in Lahore")["intent"], "unsupported")


class RevisionAndAnswerTests(unittest.TestCase):
    def test_revision_merges_into_session(self):
        revised = PARSER.parse("Change the budget to 2,000 rupees", session=SESSION)
        self.assertEqual(revised["intent"], "revise_basket")
        self.assertEqual(revised["budget_minor"], 200000)
        self.assertEqual(revised["recipe_id"], "foodcom_3474")
        self.assertEqual(PARSER.parse("Remove the olive oil", session=SESSION)["exclusions"], ["olive_oil"])

    def test_context_rule_needs_a_session_for_revisions(self):
        trace = PARSER.parse_with_trace("Change the budget to 2,000 rupees")
        self.assertNotEqual(trace["request"]["intent"], "revise_basket")
        no_rules = build_baseline_parser(CATALOG, {**CONFIG, "parser": {**CONFIG["parser"], "context_rules": False}},
                                         ROOT)
        self.assertEqual(no_rules.parse("Change the budget to 2,000 rupees")["intent"],
                         trace["classifier_intent"])

    def test_answers_fill_the_missing_field(self):
        pending = PARSER.parse("Make homemade pasta, there's a bit of plain flour in my pantry")
        self.assertEqual(PARSER.answer(pending, "150 g")["pantry"], {"white_flour": "150.000"})
        self.assertEqual(PARSER.answer(pending, "150")["pantry"], {"white_flour": "150.000"})  # the line's unit
        pending = PARSER.parse("Make homemade pasta, keep it cheap")
        answered = PARSER.answer(pending, "about Rs 900")
        self.assertEqual((answered["budget_minor"], answered["needs_clarification"]), (90000, False))
        pending = PARSER.parse("Make homemade pasta, keep it keto")
        self.assertEqual(PARSER.answer(pending, "no restrictions, just normal")["diet"], [])
        self.assertEqual(PARSER.answer(pending, "vegetarian please")["diet"], ["vegetarian"])
        pending = PARSER.parse("I want to make lasagna")
        self.assertEqual(PARSER.answer(pending, "the homemade pasta")["recipe_id"], "foodcom_3474")


class ProtocolTests(unittest.TestCase):
    def test_intent_model_sees_only_training_examples(self):
        train = split_rows(ROOT / CONFIG["data"]["nlu"], ROOT / CONFIG["data"]["nlu_split"], "train")
        self.assertEqual(len(train), 600)
        self.assertEqual(int(PARSER.intent_model.named_steps["svc"].coef_.shape[0]), 4)
        self.assertEqual(len(PARSER.intent_model.named_steps["tfidf"].vocabulary_) > 0, True)

    def test_api_and_unknown_parser(self):
        request = parse_request("Make homemade pasta for 2", CATALOG)
        self.assertEqual((request["recipe_id"], request["servings"]), ("foodcom_3474", 2))
        with self.assertRaises(ValueError):
            parse_request("hello", CATALOG, parser="gpt")

    def test_frozen_config_is_the_tuning_choice(self):
        tuning = json.loads((ROOT / CONFIG["outputs"]["intent_tuning"]).read_text(encoding="utf-8"))
        self.assertTrue(tuning["matches_frozen_config"])
        self.assertEqual(tuning["selected"], CONFIG["parser"]["intent_model"])
        self.assertEqual((tuning["train_examples"], tuning["dev_examples"]), (600, 150))

    def test_predictions_cover_only_validation_examples(self):
        dev = {r["id"] for r in split_rows(ROOT / CONFIG["data"]["nlu"], ROOT / CONFIG["data"]["nlu_split"], "dev")}
        rows = [json.loads(x) for x in (ROOT / CONFIG["outputs"]["nlu_predictions"]).read_text(encoding="utf-8").splitlines()]
        self.assertEqual({r["id"] for r in rows}, dev)

    def test_committed_metrics_match_predictions(self):
        dev = split_rows(ROOT / CONFIG["data"]["nlu"], ROOT / CONFIG["data"]["nlu_split"], "dev")
        rows = [json.loads(x) for x in (ROOT / CONFIG["outputs"]["nlu_predictions"]).read_text(encoding="utf-8").splitlines()]
        metrics = json.loads((ROOT / CONFIG["outputs"]["nlu_metrics"]).read_text(encoding="utf-8"))
        self.assertEqual(slot_metrics([d["spans"] for d in dev], [r["pred_spans"] for r in rows]), metrics["slots"])
        self.assertEqual(attachment_accuracy([d["spans"] for d in dev], [r["pred_spans"] for r in rows]),
                         metrics["quantity_attachment"])
        self.assertEqual(sum(r["request_match"] for r in rows), metrics["request_exact_match"]["correct"])


if __name__ == "__main__":
    unittest.main()
