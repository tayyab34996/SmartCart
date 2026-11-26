"""Run the E0 baseline on the validation data (Phase 5, D3).

Usage:
    python scripts/run_baseline.py --config configs/experiments/E0.json
    python scripts/run_baseline.py --config configs/experiments/E0.json --check

Steps (all deterministic):
1. Intent tuning: every grid entry in the config is trained on the 600 training examples
   and scored on the 150 validation examples. The best entry must equal the frozen
   ``parser.intent_model``; otherwise the run stops, so the config is never silently changed.
2. NLU validation: the frozen parser on the 150 validation examples (predictions + metrics).
3. Basket validation: the 50 ``basket_dev`` scenarios in two modes, ``gold_input``
   (gold StructuredRequest, component-isolated) and ``end_to_end`` (parsed from text).
4. Reference requests: the five hand-calculated D3 requests on the pilot catalog.

Test files are never read. ``--check`` rebuilds every output in memory and compares it
with the committed file byte for byte (latency is excluded because it is timing data).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402

from smartcart.benchmarks.reference import generate_baseline_reference_scenarios  # noqa: E402
from smartcart.data.contracts import load_catalog, load_pilot  # noqa: E402
from smartcart.nlu.api import build_baseline_parser, split_rows  # noqa: E402
from smartcart.nlu.baseline_parser import INTENTS, train_intent_model  # noqa: E402
from smartcart.nlu.metrics import (  # noqa: E402
    attachment_accuracy, clarification_metrics, comparable_request, field_metrics, intent_metrics,
    request_exact_match, slot_metrics,
)
from smartcart.pipeline.e0 import NO_BASKET_STATUSES, run_e0_scenario, score_e0_scenario, select_e0_basket  # noqa: E402

MODES = ("gold_input", "end_to_end")


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n"


def jsonl_text(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 6) if den else None


# ---------------------------------------------------------------- 1. intent tuning
def grid_config(entry: dict, frozen: dict) -> dict:
    vec = {"sublinear_tf": frozen["vectorizer"].get("sublinear_tf", True), "min_df": frozen["vectorizer"].get("min_df", 1),
           **entry["vectorizer"]}
    clf = {"type": "LinearSVC", "random_state": frozen["classifier"].get("random_state", 0), **entry["classifier"]}
    return {"vectorizer": vec, "classifier": clf}


def tune_intent(train: list[dict], dev: list[dict], config: dict) -> dict:
    frozen = config["parser"]["intent_model"]
    labels = list(INTENTS)
    results = []
    for entry in config["intent_tuning"]["grid"]:
        candidate = grid_config(entry, frozen)
        model = train_intent_model([r["text"] for r in train], [r["intent"] for r in train], candidate)
        pred = [str(p) for p in model.predict([r["text"] for r in dev])]
        scores = intent_metrics([r["intent"] for r in dev], pred, labels)
        results.append({"config": candidate, "dev_macro_f1": scores["macro_f1"], "dev_accuracy": scores["accuracy"]})
    best = max(range(len(results)), key=lambda i: (results[i]["dev_macro_f1"], -i))
    return {"selection": config["intent_tuning"]["selection"], "train_examples": len(train), "dev_examples": len(dev),
            "grid": results, "selected_index": best, "selected": results[best]["config"],
            "matches_frozen_config": results[best]["config"] == frozen}


# ---------------------------------------------------------------- 2. NLU validation
def nlu_validation(parser, dev: list[dict]) -> tuple[list[dict], dict]:
    rows, traces = [], []
    for ex in dev:
        trace = parser.parse_with_trace(ex["text"], session=ex["session"], request_id=ex["id"])
        traces.append(trace)
        rows.append({"id": ex["id"], "seed_id": ex["seed_id"], "family_id": ex["family_id"], "design": ex["design"],
                     "text": ex["text"], "gold_intent": ex["intent"], "classifier_intent": trace["classifier_intent"],
                     "pred_intent": trace["request"]["intent"], "intent_scores": trace["intent_scores"],
                     "pred_spans": trace["spans"], "pred_request": trace["request"],
                     "request_match": comparable_request(trace["request"]) == comparable_request(ex["gold"])})
    labels = list(INTENTS)
    gold_req = [ex["gold"] for ex in dev]
    pred_req = [t["request"] for t in traces]
    by_design = {}
    for row in rows:
        entry = by_design.setdefault(row["design"], [0, 0])
        entry[0] += 1
        entry[1] += row["request_match"]
    metrics = {
        "run": "E0", "split": "dev", "examples": len(dev),
        "intent_classifier_only": intent_metrics([ex["intent"] for ex in dev], [t["classifier_intent"] for t in traces],
                                                 labels),
        "intent": intent_metrics([ex["intent"] for ex in dev], [t["request"]["intent"] for t in traces], labels),
        "slots": slot_metrics([ex["spans"] for ex in dev], [t["spans"] for t in traces]),
        "quantity_attachment": attachment_accuracy([ex["spans"] for ex in dev], [t["spans"] for t in traces]),
        "budget": field_metrics(gold_req, pred_req, "budget_minor"),
        "servings": field_metrics(gold_req, pred_req, "servings"),
        "clarification": clarification_metrics(gold_req, pred_req),
        "request_exact_match": request_exact_match(gold_req, pred_req),
        "request_exact_match_by_design": {d: {"examples": n, "correct": c} for d, (n, c) in sorted(by_design.items())},
    }
    return rows, metrics


# ---------------------------------------------------------------- 3. basket validation
def summarize(rows: list[dict]) -> dict:
    by_label = {}
    for label in ("feasible", "infeasible", "clarification"):
        sub = [r for r in rows if r["label"] == label]
        by_label[label] = {"scenarios": len(sub), "success": sum(r["score"]["success"] for r in sub),
                           "success_rate": _rate(sum(r["score"]["success"] for r in sub), len(sub)),
                           "statuses": dict(sorted(Counter(r["status"] for r in sub).items()))}
    feasible = [r for r in rows if r["label"] == "feasible"]
    clar = [r for r in rows if r["label"] == "clarification"]
    others = [r for r in rows if r["label"] != "clarification"]
    valid_outputs = [r for r in rows if r["score"]["labelled_valid"]]
    lines = [line for r in rows for line in r["basket"].get("lines", [])]
    failure_causes = Counter()
    for r in feasible:
        if r["score"]["success"]:
            continue
        validator = r["score"]["validator"]
        if r["status"] == "valid" and validator:
            failure_causes.update("valid_but_" + v["type"] for v in validator["violations"])
        else:
            failure_causes[r["status"]] += 1
    history = [r for r in rows if r["has_history"]]
    return {
        "scenarios": len(rows),
        "by_label": by_label,
        "valid_complete_success_feasible": by_label["feasible"]["success_rate"],
        "mean_coverage_feasible": round(sum(r["score"]["coverage"] for r in feasible) / len(feasible), 6)
        if feasible else None,
        "false_rejections_feasible": sum(r["status"] in NO_BASKET_STATUSES for r in feasible),
        "infeasible_detected": by_label["infeasible"]["success"],
        "clarification_success_within_turns": by_label["clarification"]["success"],
        "clarification_asked": sum(r["score"]["asked_clarification"] for r in clar),
        "clarification_type_match": sum(bool(r["score"]["clarification_type_match"]) for r in clar),
        "unnecessary_clarifications": sum(r["score"]["asked_clarification"] for r in others),
        "outputs_labelled_valid": len(valid_outputs),
        "violations_among_valid": sum(r["score"]["violation_among_valid"] for r in rows),
        "violation_types_among_valid": dict(sorted(Counter(
            v["type"] for r in valid_outputs if r["score"]["violation_among_valid"]
            for v in r["score"]["validator"]["violations"]).items())),
        "feasible_failure_causes": dict(sorted(failure_causes.items())),
        "candidate_pool": {"lines": len(lines),
                           "no_compatible_candidate": sum(x["line_status"] == "no_candidate_in_pool" for x in lines),
                           "removed_by_diet_filter": sum(x["line_status"] == "removed_by_diet_filter" for x in lines)},
        "has_history_subset": {"scenarios": len(history), "success": sum(r["score"]["success"] for r in history)},
    }


def basket_validation(parser, catalog: dict, scenarios: list[dict], config: dict) -> tuple[dict, dict, dict]:
    method, top_k = config["retrieval"]["method"], config["retrieval"]["top_k"]
    rows_by_mode, metrics, timings = {}, {"run": "E0", "split": "dev", "policy": "docs/benchmark_policy.md"}, {}
    for mode in MODES:
        rows, times = [], []
        for scenario in scenarios:
            start = time.perf_counter()
            result = run_e0_scenario(scenario, catalog, parser, mode, method=method, top_k=top_k,
                                     max_turns=config["max_clarification_turns"])
            times.append(time.perf_counter() - start)
            result["has_history"] = scenario["has_history"]
            result["score"] = score_e0_scenario(result, scenario, catalog)
            rows.append(result)
        rows_by_mode[mode] = rows
        metrics[mode] = summarize(rows)
        timings[mode] = times
    return rows_by_mode, metrics, timings


# ---------------------------------------------------------------- 4. reference requests
def reference_request(scenario: dict) -> dict:
    req = scenario["request"]
    items = [{"ingredient_id": r["ingredient_id"], "amount": r["required_amount"], "unit": r["unit"]}
             for r in req.get("requirements", [])]
    return {"request_id": scenario["id"], "intent": "plan_meal" if req.get("recipe_id") else "build_grocery_list",
            "recipe_id": req.get("recipe_id"), "servings": req.get("servings"), "items": items,
            "pantry": dict(req.get("pantry", {})), "budget_minor": req.get("budget_minor"), "currency": "PKR",
            "diet": [], "exclusions": [], "user_id": None, "needs_clarification": False, "clarification_type": None,
            "clarification_prompt": None}


def reference_baskets(pilot: dict, config: dict) -> dict:
    out = []
    for scenario in generate_baseline_reference_scenarios():
        request = reference_request(scenario)
        basket = select_e0_basket(request, pilot, method=config["retrieval"]["method"], top_k=config["retrieval"]["top_k"])
        line_key = lambda x: (x["ingredient_id"], x["product_id"], x["pack_count"], x["line_cost_minor"])  # noqa: E731
        expected = sorted(line_key(x) for x in scenario["expected_lines"] if x["product_id"] is not None)
        actual = sorted(line_key(x) for x in basket["purchased"])
        checks = {"status": basket["status"] == scenario["expected_status"],
                  "total": basket["total_cost_minor"] == scenario["expected_total_cost_minor"],
                  "lines": actual == expected}
        out.append({"scenario_id": scenario["id"], "description": scenario["description"], "request": request,
                    "expected_status": scenario["expected_status"],
                    "expected_total_cost_minor": scenario["expected_total_cost_minor"], "status": basket["status"],
                    "total_cost_minor": basket["total_cost_minor"], "purchased": basket["purchased"],
                    "covered_by_pantry": basket["covered_by_pantry"], "checks": checks, "matches_expected": all(checks.values())})
    return {"run": "E0", "catalog": config["data"]["pilot_catalog"], "price_note": "SIMULATED PKR prices",
            "scenarios": out, "all_match": all(s["matches_expected"] for s in out)}


# ---------------------------------------------------------------- driver
def build(config: dict) -> tuple[dict[str, str], dict, object]:
    data = config["data"]
    if config["evaluated_splits"] != ["dev"]:
        raise ValueError("Phase 5 evaluates on dev only; the test sets wait for Phase 11")
    catalog = load_catalog(ROOT / data["catalog"])
    pilot = load_pilot(ROOT / data["pilot_catalog"])
    train = split_rows(ROOT / data["nlu"], ROOT / data["nlu_split"], "train")
    dev = split_rows(ROOT / data["nlu"], ROOT / data["nlu_split"], "dev")
    basket = json.loads((ROOT / data["basket_dev"]).read_text(encoding="utf-8"))
    if basket["split"] != "dev":
        raise ValueError("basket file is not the dev split")

    tuning = tune_intent(train, dev, config)
    if not tuning["matches_frozen_config"]:
        raise SystemExit(f"best grid entry {tuning['selected']} differs from the frozen config; update E0.json on purpose")

    load_start = time.perf_counter()
    parser = build_baseline_parser(catalog, config, ROOT)
    select_e0_basket(deepcopy(basket["scenarios"][0]["gold_request"]), catalog, top_k=config["retrieval"]["top_k"])
    cold_load = time.perf_counter() - load_start

    nlu_rows, nlu_metrics = nlu_validation(parser, dev)
    rows_by_mode, basket_metrics, timings = basket_validation(parser, catalog, basket["scenarios"], config)
    reference = reference_baskets(pilot, config)

    outputs = config["outputs"]
    files = {
        outputs["intent_tuning"]: json_text(tuning),
        outputs["nlu_predictions"]: jsonl_text(nlu_rows),
        outputs["nlu_metrics"]: json_text(nlu_metrics),
        outputs["basket_metrics"]: json_text(basket_metrics),
        outputs["reference_baskets"]: json_text(reference),
    }
    for mode, rows in rows_by_mode.items():
        files[outputs["basket_predictions"].format(mode=mode)] = jsonl_text(rows)

    def quantiles(values: list[float]) -> dict:
        ordered = sorted(values)
        pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
        return {"p50_s": round(statistics.median(ordered), 6), "p95_s": round(pick(0.95), 6),
                "max_s": round(ordered[-1], 6), "scenarios": len(ordered)}

    latency = {"run": "E0", "split": "dev", "note": "wall time on the build machine; not part of --check",
               "cold_load_s": round(cold_load, 6), **{f"warm_{m}": quantiles(t) for m, t in timings.items()}}
    return files, latency, parser.intent_model


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/experiments/E0.json")
    ap.add_argument("--check", action="store_true", help="rebuild and compare with the committed outputs")
    args = ap.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    files, latency, model = build(config)
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    (ROOT / config["outputs"]["latency"]).write_text(json_text(latency), encoding="utf-8", newline="\n")
    model_path = ROOT / config["outputs"]["intent_model"]
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    nlu = json.loads(files[config["outputs"]["nlu_metrics"]])
    bm = json.loads(files[config["outputs"]["basket_metrics"]])
    ref = json.loads(files[config["outputs"]["reference_baskets"]])
    print(f"intent macro-F1 (classifier / final): {nlu['intent_classifier_only']['macro_f1']} / {nlu['intent']['macro_f1']}")
    print(f"slot micro-F1: {nlu['slots']['micro']['f1']}  request exact: {nlu['request_exact_match']['accuracy']}")
    for mode in MODES:
        m = bm[mode]
        print(f"{mode}: feasible {m['by_label']['feasible']['success']}/{m['by_label']['feasible']['scenarios']}, "
              f"infeasible {m['infeasible_detected']}/{m['by_label']['infeasible']['scenarios']}, "
              f"clarification {m['clarification_success_within_turns']}/{m['by_label']['clarification']['scenarios']}, "
              f"violations among valid {m['violations_among_valid']}/{m['outputs_labelled_valid']}")
    print(f"reference requests matching hand calculation: {sum(s['matches_expected'] for s in ref['scenarios'])}/5")
    print(f"latency: {latency}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
