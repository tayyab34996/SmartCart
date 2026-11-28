"""Component test results deferred from Phases 6–8 (Phase 11, D9).

Usage:
    python scripts/evaluate_components.py             # the test split (frozen configs)
    python scripts/evaluate_components.py --check     # rebuild and compare
    python scripts/evaluate_components.py --split dev # development sanity run

- **NLU** (Phase 6): the E0 baseline parser and DistilBERT (every seed) on the NLU test
  split, with the same metrics as ``scripts/evaluate_nlu.py``.
- **Retrieval** (Phase 7): ``retrieval_test.json`` for E0's TF-IDF text, TF-IDF with the
  Phase 7 text, and MiniLM with the Phase 7 text, scored as in
  ``scripts/evaluate_retrieval.py``.
- **Track B** (Phase 8): each user's final order, ranked by popularity, personal
  frequency and frequency + association with the frozen ``configs/associations.json``
  (rules from training orders only; history = training and validation orders).

On the test split the locked files are checked first. Outputs:
``results/metrics/test_components.json`` and per-example rows in
``results/predictions/runs/`` (Track B per-user lists stay in the ignored
``data/interim/trackb/``).
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from smartcart.data.contracts import load_catalog  # noqa: E402
from smartcart.nlu import api as nlu_api  # noqa: E402
from smartcart.nlu.baseline_parser import INTENTS  # noqa: E402
from smartcart.nlu.metrics import (  # noqa: E402
    attachment_accuracy, clarification_metrics, comparable_request, field_metrics, intent_metrics,
    request_exact_match, slot_metrics,
)
from smartcart.pipeline.experiment import json_text, jsonl_text, verify_lock  # noqa: E402

NLU_SUMMARY = {
    "intent_macro_f1": lambda m: m["intent"]["macro_f1"],
    "intent_macro_f1_classifier_only": lambda m: m["intent_classifier_only"]["macro_f1"],
    "slot_micro_f1": lambda m: m["slots"]["micro"]["f1"],
    "request_exact_match": lambda m: m["request_exact_match"]["accuracy"],
}


def nlu_eval(parser, examples: list[dict]) -> tuple[list[dict], dict]:
    rows, traces = [], []
    for ex in examples:
        trace = parser.parse_with_trace(ex["text"], session=ex["session"], request_id=ex["id"])
        traces.append(trace)
        rows.append({"id": ex["id"], "family_id": ex["family_id"], "design": ex["design"], "text": ex["text"],
                     "gold_intent": ex["intent"], "classifier_intent": trace["classifier_intent"],
                     "pred_intent": trace["request"]["intent"], "pred_spans": trace["spans"],
                     "pred_request": trace["request"],
                     "request_match": comparable_request(trace["request"]) == comparable_request(ex["gold"])})
    gold_req, pred_req = [e["gold"] for e in examples], [t["request"] for t in traces]
    metrics = {
        "examples": len(examples),
        "intent_classifier_only": intent_metrics([e["intent"] for e in examples],
                                                 [t["classifier_intent"] for t in traces], list(INTENTS)),
        "intent": intent_metrics([e["intent"] for e in examples], [t["request"]["intent"] for t in traces],
                                 list(INTENTS)),
        "slots": slot_metrics([e["spans"] for e in examples], [t["spans"] for t in traces]),
        "quantity_attachment": attachment_accuracy([e["spans"] for e in examples], [t["spans"] for t in traces]),
        "budget": field_metrics(gold_req, pred_req, "budget_minor"),
        "servings": field_metrics(gold_req, pred_req, "servings"),
        "clarification": clarification_metrics(gold_req, pred_req),
        "request_exact_match": request_exact_match(gold_req, pred_req),
    }
    return rows, metrics


def nlu_section(catalog, evaluation, split, out, files) -> dict:
    examples = nlu_api.split_rows(ROOT / evaluation["data"]["nlu"], ROOT / evaluation["data"]["nlu_split"], split)
    section = {"examples": len(examples)}
    rows, section["baseline"] = nlu_eval(nlu_api.get_parser(catalog, "baseline"), examples)
    files[out["nlu_rows"].format(parser="baseline", seed="")] = jsonl_text(rows)
    config = json.loads(nlu_api.TRANSFORMER_CONFIG.read_text(encoding="utf-8"))
    per_seed = {}
    for seed in evaluation["seeds"]:
        parser = nlu_api.load_transformer_parser(catalog, config, seed, ROOT)
        rows, per_seed[str(seed)] = nlu_eval(parser, examples)
        files[out["nlu_rows"].format(parser="transformer", seed=f"_seed{seed}")] = jsonl_text(rows)
        del parser
        gc.collect()
    section["transformer"] = {"per_seed": per_seed, "summary": {
        name: {"mean": round(statistics.mean(get(m) for m in per_seed.values()), 6),
               "std": round(statistics.pstdev(get(m) for m in per_seed.values()), 6),
               "per_seed": {s: get(m) for s, m in per_seed.items()}} for name, get in NLU_SUMMARY.items()}}
    section["baseline_summary"] = {name: get(section["baseline"]) for name, get in NLU_SUMMARY.items()}
    return section


def retrieval_section(catalog, evaluation, split, out, files) -> dict:
    from smartcart.retrieval.benchmark import evaluate, load_queries

    queries = load_queries(ROOT / evaluation["data"]["retrieval"][split], split)
    section = {"queries": len(queries)}
    for setting in evaluation["retrieval_settings_for_components"]:
        result = evaluate(queries, catalog, setting["method"], setting["product_text"], [5, 10, 20, 40])
        files[out["retrieval_rows"].format(name=setting["name"])] = jsonl_text(result["rows"])
        section[setting["name"]] = {**{k: setting[k] for k in ("method", "product_text")}, **result["summary"]}
    return section


def trackb_section(catalog, evaluation, split) -> tuple[dict, dict]:
    from smartcart.associations.mining import mine_itemsets, mine_rules, one_hot, pair_matrix, pair_table
    from smartcart.associations.trackb import (
        RANKERS, build_users, evaluate, paired_bootstrap, popularity, scores, summarize, top_k,
    )
    from smartcart.associations.transactions import load_trackb

    cfg = json.loads((ROOT / evaluation["track_b"]["config"]).read_text(encoding="utf-8"))
    d = cfg["data"]
    target = {"test": "test", "dev": "validation"}[split]
    history = ("train", "validation") if target == "test" else ("train",)
    trackb = load_trackb(catalog, ROOT / d["trackb"], ROOT / d["mapping"], ROOT / d["baskets"],
                         splits=("train", "validation", "test") if target == "test" else ("train", "validation"))
    train = [trackb.orders[o] for o in trackb.split_orders("train")]
    frame = one_hot(train, trackb.items)
    pairs = pair_table(mine_rules(mine_itemsets(frame, cfg["mining"]["min_count_floor"], cfg["mining"]["max_len"]),
                                  len(frame)))
    sel = cfg["selection"]["selected"]
    matrix = pair_matrix(pairs, trackb.items, sel["min_count"], sel["min_confidence"])
    pop = popularity(trackb, ("train",))
    users, excluded = build_users(trackb, target, history)
    results, per_user, lists = {}, {}, {}
    for ranker in RANKERS:
        ranked = top_k(scores(ranker, users, matrix, sel["weight"]), pop, 10)
        rows = evaluate(ranked, users, 10)
        results[ranker], per_user[ranker], lists[ranker] = summarize(rows), rows, ranked
    boot = cfg["trackb"]["bootstrap"]
    bootstrap = {}
    for a, b in (("association", "frequency"), ("frequency", "popularity")):
        for metric in ("ndcg", "recall"):
            bootstrap[f"{a}_minus_{b}_{metric}_at_10"] = paired_bootstrap(
                [r["all"][metric] for r in per_user[a]], [r["all"][metric] for r in per_user[b]],
                boot["resamples"], boot["seed"])
    section = {"target": f"{target} order", "history": list(history), "rules": "training orders only",
               "selection": sel, "users": {"sampled": len(trackb.user_orders), "excluded_empty_target": excluded,
                                           "evaluated": len(users.ids)},
               "results": results, "bootstrap": bootstrap}
    predictions = {ranker: [{"user_id": u, "top10": [trackb.items[i] for i in lists[ranker][r]]}
                            for r, u in enumerate(users.ids)] for ranker in RANKERS}
    return section, predictions


def build(evaluation: dict, split: str) -> tuple[dict, dict, dict]:
    if split == "test":
        lock = verify_lock(ROOT, ROOT / evaluation["lock"])
        if not all(lock.values()):
            raise SystemExit(f"locked files changed, refusing to evaluate: {lock}")
    catalog = load_catalog(ROOT / evaluation["data"]["catalog"])
    out = dict(evaluation["outputs"])
    if split != "test":
        for key in ("components", "nlu_rows", "retrieval_rows"):
            out[key] = f"{evaluation['outputs']['dev_sanity']}/{Path(out[key]).name}"
    files = {}
    record = {"split": split, "nlu": nlu_section(catalog, evaluation, split, out, files),
              "retrieval": retrieval_section(catalog, evaluation, split, out, files)}
    record["track_b"], predictions = trackb_section(catalog, evaluation, split)
    files[out["components"]] = json_text(record)
    return files, record, predictions


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evaluation", default="configs/experiments/evaluation.json")
    ap.add_argument("--split", choices=["test", "dev"], default=None)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    evaluation = json.loads((ROOT / args.evaluation).read_text(encoding="utf-8"))
    split = args.split or evaluation["split"]
    files, record, predictions = build(evaluation, split)
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    target = ROOT / "data" / "interim" / "trackb"
    target.mkdir(parents=True, exist_ok=True)
    for ranker, rows in predictions.items():
        (target / f"{split}_{ranker}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                                        encoding="utf-8", newline="\n")
    n = record["nlu"]
    print(f"NLU [{split}] baseline: {json.dumps(n['baseline_summary'])}")
    print(f"NLU [{split}] transformer: " + json.dumps({k: v['mean'] for k, v in n['transformer']['summary'].items()}))
    for name in ("tfidf_legacy_top10", "tfidf", "minilm"):
        r = record["retrieval"][name]
        print(f"retrieval [{split}] {name}: R@5 {r['recall_at_5']} R@10 {r['recall_at_10']} MRR {r['mrr']}")
    for ranker, r in record["track_b"]["results"].items():
        print(f"Track B [{split}] {ranker}: R@10 {r['all']['recall_at_10']} NDCG@10 {r['all']['ndcg_at_10']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
