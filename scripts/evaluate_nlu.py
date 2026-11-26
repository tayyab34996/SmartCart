"""Calibrate and evaluate the DistilBERT parser against E0 on validation data (Phase 6).

Usage:
    python scripts/evaluate_nlu.py --calibrate   # fit temperature + threshold per seed, write them to the config
    python scripts/evaluate_nlu.py               # evaluate with the frozen calibration
    python scripts/evaluate_nlu.py --check       # rebuild outputs in memory and compare with the committed files

Needs the checkpoints from ``scripts/train_nlu.py``. Only the train (for E0) and dev
splits are read. Outputs:
- ``results/predictions/nlu_dev_transformer_seed<seed>.jsonl``;
- ``results/metrics/nlu_dev.json``: both parsers, every seed, mean and spread;
- ``results/metrics/nlu_calibration.json``: temperature, ECE before/after, threshold grid;
- figures ``09_nlu_intent_confusion_matrix.png`` and ``10_nlu_training_curves.png``
  (drawn from the saved predictions and training log; not part of ``--check``).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from smartcart.data.contracts import load_catalog  # noqa: E402
from smartcart.nlu.api import build_baseline_parser, load_transformer_parser, split_rows  # noqa: E402
from smartcart.nlu.baseline_parser import INTENTS  # noqa: E402
from smartcart.nlu.metrics import (  # noqa: E402
    attachment_accuracy, clarification_metrics, comparable_request, field_metrics, intent_metrics,
    request_exact_match, slot_metrics,
)
from smartcart.nlu.transformer_parser import (  # noqa: E402
    INTENT_ID, choose_threshold, expected_calibration_error, fit_temperature, nll, softmax,
)

PREDICTIONS = "results/predictions/nlu_dev_transformer_seed{seed}.jsonl"
METRICS = "results/metrics/nlu_dev.json"
CALIBRATION = "results/metrics/nlu_calibration.json"
FIGURE_09 = "results/figures/09_nlu_intent_confusion_matrix.png"
FIGURE_10 = "results/figures/10_nlu_training_curves.png"
SUMMARY_KEYS = {
    "intent_macro_f1_classifier": lambda m: m["intent_classifier_only"]["macro_f1"],
    "intent_macro_f1": lambda m: m["intent"]["macro_f1"],
    "slot_micro_f1": lambda m: m["slots"]["micro"]["f1"],
    "quantity_attachment": lambda m: m["quantity_attachment"]["accuracy"],
    "budget_exact": lambda m: m["budget"]["exact_accuracy"],
    "servings_exact": lambda m: m["servings"]["exact_accuracy"],
    "clarification_type_accuracy": lambda m: m["clarification"]["type_accuracy"],
    "unnecessary_clarifications": lambda m: m["clarification"]["unnecessary"],
    "request_exact_match": lambda m: m["request_exact_match"]["accuracy"],
}


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n"


def evaluate_parser(parser, dev: list[dict]) -> tuple[list[dict], dict]:
    rows, traces = [], []
    for ex in dev:
        trace = parser.parse_with_trace(ex["text"], session=ex["session"], request_id=ex["id"])
        traces.append(trace)
        rows.append({"id": ex["id"], "design": ex["design"], "text": ex["text"], "gold_intent": ex["intent"],
                     "classifier_intent": trace["classifier_intent"], "pred_intent": trace["request"]["intent"],
                     "intent_probabilities": trace["intent_scores"], "pred_spans": trace["spans"],
                     "pred_request": trace["request"],
                     "request_match": comparable_request(trace["request"]) == comparable_request(ex["gold"])})
    labels = list(INTENTS)
    gold_req, pred_req = [ex["gold"] for ex in dev], [t["request"] for t in traces]
    metrics = {
        "examples": len(dev),
        "intent_classifier_only": intent_metrics([e["intent"] for e in dev], [t["classifier_intent"] for t in traces],
                                                 labels),
        "intent": intent_metrics([e["intent"] for e in dev], [t["request"]["intent"] for t in traces], labels),
        "slots": slot_metrics([e["spans"] for e in dev], [t["spans"] for t in traces]),
        "quantity_attachment": attachment_accuracy([e["spans"] for e in dev], [t["spans"] for t in traces]),
        "budget": field_metrics(gold_req, pred_req, "budget_minor"),
        "servings": field_metrics(gold_req, pred_req, "servings"),
        "clarification": clarification_metrics(gold_req, pred_req),
        "low_confidence_questions": sum(t["request"]["clarification_type"] == "low_confidence_intent" for t in traces),
        "request_exact_match": request_exact_match(gold_req, pred_req),
    }
    return rows, metrics


def calibrate(config: dict, catalog: dict, dev: list[dict]) -> dict:
    g = config["temperature_grid"]
    grid = [round(g["start"] + i * g["step"], 6) for i in range(int(round((g["stop"] - g["start"]) / g["step"])) + 1)]
    labels = np.array([INTENT_ID[e["intent"]] for e in dev])
    out = {"method": config["calibration_method"], "threshold_rule": config["threshold_rule"], "seeds": {}}
    for seed in config["seeds"]:
        parser = load_transformer_parser(catalog, config, seed, ROOT, calibrated=False)
        logits = parser.intent_model.logits([e["text"] for e in dev])
        temperature = fit_temperature(logits, labels, grid)
        probs = softmax(logits, temperature)
        # The threshold applies where the classifier decided the final intent (no context rule fired).
        confidence, correct = [], []
        for ex, p in zip(dev, probs):
            trace = parser.parse_with_trace(ex["text"], session=ex["session"])
            if trace["request"]["intent"] == trace["classifier_intent"]:
                confidence.append(float(p.max()))
                correct.append(trace["classifier_intent"] == ex["intent"])
        threshold = choose_threshold(confidence, correct, config["threshold_grid"])
        out["seeds"][str(seed)] = {
            "temperature": temperature,
            "nll_before": round(nll(logits, labels, 1.0), 6), "nll_after": round(nll(logits, labels, temperature), 6),
            "ece_before": expected_calibration_error(softmax(logits, 1.0), labels),
            "ece_after": expected_calibration_error(probs, labels),
            "threshold": threshold["threshold"], "threshold_grid": threshold["grid"],
            "classifier_decided_examples": len(confidence),
        }
    return out


def summary(per_seed: dict) -> dict:
    out = {}
    for name, get in SUMMARY_KEYS.items():
        values = [get(m) for m in per_seed.values()]
        out[name] = {"mean": round(statistics.mean(values), 6), "std": round(statistics.pstdev(values), 6),
                     "min": min(values), "max": max(values), "per_seed": dict(zip(per_seed, values))}
    return out


def build(config: dict) -> tuple[dict[str, str], dict]:
    catalog = load_catalog(ROOT / config["data"]["catalog"])
    dev = split_rows(ROOT / config["data"]["nlu"], ROOT / config["data"]["nlu_split"], "dev")
    e0_config = json.loads((ROOT / "configs" / "experiments" / "E0.json").read_text(encoding="utf-8"))
    files = {}
    _, baseline = evaluate_parser(build_baseline_parser(catalog, e0_config, ROOT), dev)
    per_seed = {}
    for seed in config["seeds"]:
        rows, metrics = evaluate_parser(load_transformer_parser(catalog, config, seed, ROOT), dev)
        per_seed[str(seed)] = metrics
        files[PREDICTIONS.format(seed=seed)] = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n"
                                                       for r in rows)
    result = {"split": "dev", "note": "validation data only; test is evaluated once in Phase 11 with frozen configs",
              "baseline_E0": baseline, "transformer": {"primary_seed": config["primary_seed"],
                                                       "summary": summary(per_seed), "seeds": per_seed},
              "baseline_summary": {k: get(baseline) for k, get in SUMMARY_KEYS.items()}}
    files[METRICS] = json_text(result)
    return files, result


def figures(config: dict, result: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = list(INTENTS)
    short = ["list", "plan", "revise", "unsupported"]
    pooled = np.sum([np.array(m["intent_classifier_only"]["confusion_matrix"])
                     for m in result["transformer"]["seeds"].values()], axis=0)
    panels = [("E0: TF-IDF + LinearSVC", np.array(result["baseline_E0"]["intent_classifier_only"]["confusion_matrix"])),
              (f"DistilBERT ({len(result['transformer']['seeds'])} seeds pooled)", pooled)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, (title, cm) in zip(axes, panels):
        rates = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
        ax.imshow(rates, cmap="Blues", vmin=0, vmax=1)
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, f"{int(cm[i, j])}", ha="center", va="center",
                        color="white" if rates[i, j] > 0.6 else "black", fontsize=10)
        ax.set_xticks(range(len(labels)), short)
        ax.set_yticks(range(len(labels)), short)
        ax.set_xlabel("predicted intent (classifier only)")
        ax.set_ylabel("gold intent")
        ax.set_title(title, fontsize=11)
    fig.suptitle("Intent confusion on the 150 validation examples (counts; shading = row share)", fontsize=11)
    fig.tight_layout()
    fig.savefig(ROOT / FIGURE_09, dpi=150, metadata={"Software": None})
    plt.close(fig)

    log = json.loads((ROOT / config["training_log"]).read_text(encoding="utf-8"))
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for col, task in enumerate(("intent", "slots")):
        for seed in config["seeds"]:
            run = log["runs"].get(f"seed{seed}_{task}")
            if not run:
                continue
            ep = [e["epoch"] for e in run["epochs"]]
            axes[0, col].plot(ep, [e["train_loss"] for e in run["epochs"]], marker="o", label=f"seed {seed} train")
            axes[0, col].plot(ep, [e["dev_loss"] for e in run["epochs"]], marker="x", linestyle="--",
                              label=f"seed {seed} dev")
            axes[1, col].plot(ep, [e["dev_score"] for e in run["epochs"]], marker="o", label=f"seed {seed}")
            axes[1, col].axvline(run["best_epoch"], color=axes[1, col].lines[-1].get_color(), alpha=0.3)
        axes[0, col].set_title(f"{task}: loss per epoch")
        axes[1, col].set_title(f"{task}: dev {'macro-F1' if task == 'intent' else 'slot micro-F1'} "
                               "(vertical line = kept epoch)")
        axes[1, col].set_xlabel("epoch")
        for row in (0, 1):
            axes[row, col].legend(fontsize=7)
            axes[row, col].grid(alpha=0.3)
    fig.suptitle("DistilBERT fine-tuning, logged by scripts/train_nlu.py (CPU)", fontsize=11)
    fig.tight_layout()
    fig.savefig(ROOT / FIGURE_10, dpi=150, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/nlu_transformer.json")
    ap.add_argument("--calibrate", action="store_true", help="fit and freeze the calibration in the config")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config_path = ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    torch.set_num_threads(config["torch_threads"])
    catalog = load_catalog(ROOT / config["data"]["catalog"])
    dev = split_rows(ROOT / config["data"]["nlu"], ROOT / config["data"]["nlu_split"], "dev")
    calibration = calibrate(config, catalog, dev)
    frozen = {s: {"temperature": c["temperature"], "threshold": c["threshold"]} for s, c in calibration["seeds"].items()}
    if args.calibrate:
        config["calibration"] = frozen
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("frozen calibration:", frozen)
    elif frozen != config["calibration"]:
        raise SystemExit(f"calibration {frozen} differs from the frozen config; run --calibrate on purpose")
    files, result = build(config)
    files[CALIBRATION] = json_text(calibration)
    if args.check:
        bad = [p for p, text in files.items() if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    figures(config, result)
    s, b = result["transformer"]["summary"], result["baseline_summary"]
    for key in SUMMARY_KEYS:
        print(f"{key:32s} E0 {b[key]!s:>10}   DistilBERT {s[key]['mean']} ± {s[key]['std']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
