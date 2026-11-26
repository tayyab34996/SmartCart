"""Phase 6: DistilBERT parser pieces, calibration, training log and committed validation results.

Tests that need the fine-tuned checkpoints (``models/nlu/transformer/``, git-ignored) or the
cached base model are skipped when those are absent, e.g. on a fresh clone before
``scripts/train_nlu.py`` has been run.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.nlu.baseline_parser import suggest_recipes  # noqa: E402
from smartcart.nlu.lexicon import Lexicon, read_recipe_aliases  # noqa: E402
from smartcart.nlu.metrics import comparable_request, slot_metrics  # noqa: E402
from smartcart.nlu.normalize import SpanNormalizer  # noqa: E402
from smartcart.nlu.transformer_parser import (  # noqa: E402
    BIO_LABELS, IGNORE, choose_threshold, encode_words, expected_calibration_error, fit_temperature, nll,
    repair_bio, softmax, tags_to_spans,
)
from smartcart.validation.feasibility import check_feasibility  # noqa: E402

CONFIG = json.loads((ROOT / "configs" / "nlu_transformer.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / CONFIG["data"]["catalog"]).read_text(encoding="utf-8"))
LEXICON = Lexicon(CATALOG, read_recipe_aliases(ROOT / CONFIG["data"]["recipe_aliases"]))
ROWS = [json.loads(x) for x in (ROOT / CONFIG["data"]["nlu"]).read_text(encoding="utf-8").splitlines()]
CHECKPOINTS = all((ROOT / CONFIG["checkpoints"].format(seed=s, task=t) / "config.json").exists()
                  for s in CONFIG["seeds"] for t in ("intent", "slots"))


def base_tokenizer():
    try:
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(CONFIG["base_model"], revision=CONFIG["revision"], local_files_only=True)
    except Exception:  # noqa: BLE001 - absent cache means the test is skipped
        return None


class TaggingTests(unittest.TestCase):
    def test_repair_and_decode(self):
        self.assertEqual(repair_bio(["I-MEAL", "I-MEAL", "O", "I-UNIT"]), ["B-MEAL", "I-MEAL", "O", "B-UNIT"])
        text = "Buy 2 kg rice"
        spans = tags_to_spans(text, ["O", "B-QUANTITY", "B-UNIT", "B-PRODUCT"])
        self.assertEqual([(s["label"], s["text"]) for s in spans], [("QUANTITY", "2"), ("UNIT", "kg"), ("PRODUCT", "rice")])
        self.assertEqual(len(BIO_LABELS), 21)

    def test_first_subtoken_labelling(self):
        tokenizer = base_tokenizer()
        if tokenizer is None:
            self.skipTest("base model not cached")
        words, tags = ["Buy", "parmigiano", "cheese"], ["O", "B-PRODUCT", "I-PRODUCT"]
        enc = encode_words(tokenizer, words, tags, CONFIG["max_length"])
        labelled = [lab for lab in enc["labels"] if lab != IGNORE]
        self.assertEqual([BIO_LABELS[i] for i in labelled], tags)
        self.assertGreater(len(enc["input_ids"]), len(words) + 2)  # "parmigiano" splits into 4 sub-tokens
        with self.assertRaises(ValueError):
            encode_words(tokenizer, ["word"] * 200, ["O"] * 200, CONFIG["max_length"])

    def test_every_annotation_fits_max_length(self):
        tokenizer = base_tokenizer()
        if tokenizer is None:
            self.skipTest("base model not cached")
        for r in ROWS:
            encode_words(tokenizer, r["tokens"], r["bio_tags"], CONFIG["max_length"])


class NormalizerTests(unittest.TestCase):
    def test_reproduces_gold_values_and_attachment(self):
        n = SpanNormalizer(LEXICON)
        for r in ROWS:
            if r["split"] == "test":
                continue
            out = n.normalise([{k: s[k] for k in ("label", "start", "end", "text")} for s in r["spans"]])
            for g, o in zip(r["spans"], out):
                expected = "ambiguous" if g["label"] == "DIET" and g["value"] is None else g["value"]
                self.assertEqual((str(expected), g["attach_to"]), (str(o["value"]), o["attach_to"]), r["id"])

    def test_misspelling_and_unknown(self):
        n = SpanNormalizer(LEXICON)
        self.assertEqual(n.value("PRODUCT", "chedar cheese"), "cheddar")
        self.assertIsNone(n.value("MEAL", "lasagna"))
        self.assertEqual(n.value("DIET", "carnivore"), "ambiguous")
        self.assertEqual(n.value("BUDGET", "2.5k"), 2500)


class CalibrationTests(unittest.TestCase):
    def test_temperature_softens_overconfident_logits(self):
        rng = np.random.default_rng(0)
        labels = rng.integers(0, 4, 400)
        logits = rng.normal(0, 1, (400, 4))
        logits[np.arange(400), labels] += 1.0
        logits *= 8  # overconfident
        t = fit_temperature(logits, labels, [round(0.25 + 0.05 * i, 2) for i in range(196)])
        self.assertGreater(t, 1.0)
        self.assertLess(nll(logits, labels, t), nll(logits, labels, 1.0))
        self.assertLessEqual(expected_calibration_error(softmax(logits, t), labels),
                             expected_calibration_error(softmax(logits, 1.0), labels))

    def test_threshold_rule(self):
        chosen = choose_threshold([0.2, 0.9, 0.95, 0.35], [False, True, True, False], [0.0, 0.3, 0.4, 0.95])
        self.assertEqual(chosen["threshold"], 0.4)  # catches both errors, questions no correct intent
        self.assertEqual(choose_threshold([0.9, 0.95], [True, True], [0.0, 0.5])["threshold"], 0.0)

    def test_recipe_suggestions_are_feasible_and_cheapest_first(self):
        request = {"servings": 4, "budget_minor": 300000, "diet": ["vegetarian"]}
        rids = suggest_recipes(request, CATALOG)
        self.assertLessEqual(len(rids), 3)
        costs = []
        for rid in rids:
            result = check_feasibility({"intent": "plan_meal", "recipe_id": rid, "servings": 4, "items": [],
                                        "pantry": {}, "budget_minor": 300000, "diet": ["vegetarian"],
                                        "exclusions": []}, CATALOG)
            self.assertEqual(result["label"], "feasible")
            costs.append(result["min_cost_minor"])
        self.assertEqual(costs, sorted(costs))


class TrainingLogTests(unittest.TestCase):
    def test_log_covers_every_seed_and_task(self):
        log = json.loads((ROOT / CONFIG["training_log"]).read_text(encoding="utf-8"))
        self.assertEqual(log["revision"], CONFIG["revision"])
        for seed in CONFIG["seeds"]:
            for task in ("intent", "slots"):
                run = log["runs"][f"seed{seed}_{task}"]
                self.assertEqual((run["train_examples"], run["dev_examples"]), (600, 150))
                self.assertEqual(len(run["epochs"]), CONFIG[task]["epochs"])
                best = max(run["epochs"], key=lambda e: (e["dev_score"], -e["epoch"]))
                self.assertEqual(run["best_epoch"], best["epoch"])


@unittest.skipUnless(CHECKPOINTS, "fine-tuned checkpoints not present; run scripts/train_nlu.py")
class CheckpointTests(unittest.TestCase):
    def test_parse_request_with_transformer(self):
        from smartcart.nlu.api import parse_request
        # Punctuated like the training text. Without the commas ("for 2 under 1500") seeds 42 and 7 tag
        # "2" as a budget; that brittleness is recorded in docs/nlu_failures.md.
        request = parse_request("I want to make homemade pasta, for 2 people, under 1500 rupees", CATALOG,
                                parser="transformer")
        self.assertEqual((request["intent"], request["recipe_id"], request["servings"], request["budget_minor"]),
                         ("plan_meal", "foodcom_3474", 2, 150000))
        session = dict(request)
        revised = parse_request("Change the budget to 2,000 rupees", CATALOG, parser="transformer", session=session)
        self.assertEqual((revised["intent"], revised["budget_minor"]), ("revise_basket", 200000))

    def test_committed_metrics_match_predictions(self):
        metrics = json.loads((ROOT / "results/metrics/nlu_dev.json").read_text(encoding="utf-8"))
        dev = {r["id"]: r for r in ROWS if r["split"] == "dev"}
        for seed in CONFIG["seeds"]:
            path = ROOT / f"results/predictions/nlu_dev_transformer_seed{seed}.jsonl"
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({r["id"] for r in rows}, set(dev))
            m = metrics["transformer"]["seeds"][str(seed)]
            self.assertEqual(slot_metrics([dev[r["id"]]["spans"] for r in rows], [r["pred_spans"] for r in rows]),
                             m["slots"])
            matches = sum(comparable_request(r["pred_request"]) == comparable_request(dev[r["id"]]["gold"]) for r in rows)
            self.assertEqual(matches, m["request_exact_match"]["correct"])

    def test_frozen_calibration_and_rebuild(self):
        calibration = json.loads((ROOT / "results/metrics/nlu_calibration.json").read_text(encoding="utf-8"))
        for seed in CONFIG["seeds"]:
            frozen = CONFIG["calibration"][str(seed)]
            fitted = calibration["seeds"][str(seed)]
            self.assertEqual((frozen["temperature"], frozen["threshold"]), (fitted["temperature"], fitted["threshold"]))
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_nlu.py"), "--check"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
