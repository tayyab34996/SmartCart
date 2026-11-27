"""Track B on the validation orders: popularity vs frequency vs association (Phase 8).

Usage:
    python scripts/evaluate_trackb.py --select   # apply the selection rule on the tune half, freeze it in the config
    python scripts/evaluate_trackb.py            # evaluate with the frozen choice and write the outputs
    python scripts/evaluate_trackb.py --check    # rebuild the committed metrics in memory and compare

Reads only Track B training and validation orders (never the test orders, which are
evaluated once in Phase 11). Rules are mined on training orders only. The thresholds and
the association weight are chosen on the "tune" half of the validation users and
reported on the "report" half (and, for reference, on all validation users).
Outputs:
- ``results/metrics/trackb_validation.json``: the grid, the selection, every ranker on
  each half (all, repeat and new items) and paired bootstrap intervals;
- ``data/interim/trackb/validation_{ranker}.jsonl`` (git-ignored: derived from basket
  contents, which are not redistributed);
- figure ``13_trackb_validation.png`` (not part of ``--check``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.associations.mining import mine_itemsets, mine_rules, one_hot, pair_matrix, pair_table  # noqa: E402
from smartcart.associations.trackb import (  # noqa: E402
    RANKERS, build_users, evaluate, paired_bootstrap, popularity, scores, subset, summarize, top_k, user_half,
)
from smartcart.associations.transactions import load_trackb  # noqa: E402
from smartcart.data.contracts import load_catalog  # noqa: E402

FIGURE_13 = "results/figures/13_trackb_validation.png"
K = 10


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def load(config: dict):
    d = config["data"]
    catalog = load_catalog(ROOT / d["catalog"])
    trackb = load_trackb(catalog, ROOT / d["trackb"], ROOT / d["mapping"], ROOT / d["baskets"],
                         splits=("train", "validation"))
    return catalog, trackb


def mined_pairs(config: dict, trackb) -> dict:
    train = [trackb.orders[o] for o in trackb.split_orders("train")]
    frame = one_hot(train, trackb.items)
    itemsets = mine_itemsets(frame, config["mining"]["min_count_floor"], config["mining"]["max_len"])
    return pair_table(mine_rules(itemsets, len(frame)))


def selection_key(row: dict) -> tuple:
    return (-row["ndcg_at_10"], -row["recall_at_10"], -row["min_count"], -row["min_confidence"], row["weight"])


def rank(ranker: str, users, pop, pairs=None, weight=0.0):
    return top_k(scores(ranker, users, pairs, weight), pop, K)


def compare_lists(assoc, freq, users, items: list[str]) -> dict:
    """How the association term changes the report-half lists relative to frequency."""
    from collections import Counter

    gain = lose = same = 0
    pushed_in, pushed_out = Counter(), Counter()
    for a, f, target in zip(assoc, freq, users.targets):
        hits_a, hits_f = len(set(a) & target), len(set(f) & target)
        gain += hits_a > hits_f
        lose += hits_a < hits_f
        same += hits_a == hits_f
        pushed_in.update(items[i] for i in set(a) - set(f))
        pushed_out.update(items[i] for i in set(f) - set(a))

    def top(counter):
        return [[item, n] for item, n in sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:10]]

    return {"users_with_more_hits": gain, "users_with_fewer_hits": lose, "users_with_same_hits": same,
            "items_most_often_pushed_into_top10": top(pushed_in),
            "items_most_often_pushed_out_of_top10": top(pushed_out)}


def build(config: dict) -> tuple[dict, dict, dict, dict]:
    if "test" in json.dumps(config["evaluated_splits"]):
        raise SystemExit("Phase 8 reads training and validation orders only")
    catalog, trackb = load(config)
    pairs = mined_pairs(config, trackb)
    pop = popularity(trackb, ("train",))
    users, excluded = build_users(trackb, "validation", ("train",))
    seed = config["trackb"]["user_split"]["seed"]
    halves = [user_half(u, seed) for u in users.ids]
    tune = subset(users, [h == "tune" for h in halves])
    report = subset(users, [h == "report" for h in halves])

    grid = []
    g = config["grid"]
    for min_count in g["min_count"]:
        for min_conf in g["min_confidence"]:
            matrix = pair_matrix(pairs, trackb.items, min_count, min_conf)
            for weight in g["weight"]:
                s = summarize(evaluate(rank("association", tune, pop, matrix, weight), tune, K))["all"]
                grid.append({"min_count": min_count, "min_confidence": min_conf, "weight": weight,
                             "pairs_with_score": int((matrix > 0).sum() // 2),
                             "recall_at_10": s["recall_at_10"], "ndcg_at_10": s["ndcg_at_10"]})
    best = min(grid, key=selection_key)
    selection = {"min_count": best["min_count"], "min_confidence": best["min_confidence"], "weight": best["weight"]}
    matrix = pair_matrix(pairs, trackb.items, selection["min_count"], selection["min_confidence"])

    results, per_user, ranked_lists = {}, {}, {}
    for name, group in (("report", report), ("tune", tune), ("all_validation", users)):
        results[name] = {}
        for ranker in RANKERS:
            ranked = rank(ranker, group, pop, matrix, selection["weight"])
            rows = evaluate(ranked, group, K)
            results[name][ranker] = summarize(rows)
            per_user[(name, ranker)] = rows
            ranked_lists[(name, ranker)] = ranked
    boot = config["trackb"]["bootstrap"]
    bootstrap = {}
    for a, b in (("association", "frequency"), ("frequency", "popularity")):
        for metric in ("ndcg", "recall"):
            bootstrap[f"{a}_minus_{b}_{metric}_at_10"] = paired_bootstrap(
                [r["all"][metric] for r in per_user[("report", a)]],
                [r["all"][metric] for r in per_user[("report", b)]], boot["resamples"], boot["seed"])
    changed = sum(list(x) != list(y) for x, y in zip(ranked_lists[("report", "association")],
                                                     ranked_lists[("report", "frequency")]))
    comparison = compare_lists(ranked_lists[("report", "association")], ranked_lists[("report", "frequency")],
                               report, trackb.items)
    metrics = {
        "level": config["level"], "universe": len(trackb.items), "list_length": K,
        "target": "validation order (second-to-last usable order), mapped ingredients",
        "history": "training orders", "rules": "training orders only",
        "users": {"sampled": len(trackb.user_orders), "excluded_empty_target": excluded,
                  "evaluated": len(users.ids), "tune": len(tune.ids), "report": len(report.ids)},
        "selection": {"rule": config["selection"]["rule"], "selected": selection,
                      "pairs_with_score": best["pairs_with_score"], "grid": grid},
        "results": results,
        "bootstrap_report_half": bootstrap,
        "report_users_whose_top10_changes_with_association": changed,
        "association_vs_frequency_report_half": comparison,
    }
    predictions = {}
    items = trackb.items
    for (name, ranker), ranked in ranked_lists.items():
        if name == "tune":
            continue
        group = report if name == "report" else users
        predictions.setdefault(ranker, [])
        if name == "all_validation":
            for r, user in enumerate(group.ids):
                predictions[ranker].append({"user_id": user, "half": user_half(user, seed),
                                            "top10": [items[i] for i in ranked[r]],
                                            "target": sorted(items[i] for i in group.targets[r])})
    return {config["outputs"]["trackb_metrics"]: json_text(metrics)}, metrics, selection, predictions


def figure(metrics: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    res = metrics["results"]["report"]
    labels = {"popularity": "Popularity", "frequency": "Personal frequency", "association": "Frequency + association"}
    parts = [("all", "All items"), ("repeat", "Repeat items"), ("new", "New items")]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    x = np.arange(len(parts))
    for ax, metric, title in ((axes[0], "recall_at_10", "Recall@10"), (axes[1], "ndcg_at_10", "NDCG@10")):
        for j, ranker in enumerate(labels):
            vals = [res[ranker][p][metric] or 0.0 for p, _ in parts]
            bars = ax.bar(x + (j - 1) * 0.27, vals, 0.27, label=labels[ranker])
            ax.bar_label(bars, fmt="%.3f", fontsize=7)
        counts = [res["frequency"][p]["num_users"] for p, _ in parts]
        ax.set_xticks(x, [f"{t}\n(n={n} users)" for (_, t), n in zip(parts, counts)], fontsize=8)
        ax.set_ylim(0, 1.0)
        ax.set_title(title, fontsize=10)
    axes[0].legend(fontsize=8)
    sel = metrics["selection"]["selected"]
    fig.suptitle("Track B next-basket ranking, validation orders, report half "
                 f"(ingredient level, top {metrics['list_length']} of {metrics['universe']}; "
                 f"rules: count >= {sel['min_count']}, confidence >= {sel['min_confidence']}, weight {sel['weight']})",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / FIGURE_13, dpi=150, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/associations.json")
    ap.add_argument("--select", action="store_true", help="freeze the selected thresholds and weight")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config_path = ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    files, metrics, selection, predictions = build(config)
    if args.select:
        config["selection"]["selected"] = selection
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                               newline="\n")
        print("frozen selection:", selection)
    elif selection != config["selection"]["selected"]:
        raise SystemExit(f"selection {selection} differs from the frozen config; run --select on purpose")
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    pred_path = config["outputs"]["trackb_predictions"]
    for ranker, rows in predictions.items():
        out = ROOT / pred_path.format(ranker=ranker)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    figure(metrics)
    for ranker in RANKERS:
        r = metrics["results"]["report"][ranker]["all"]
        print(f"{ranker:12s} report half  R@10 {r['recall_at_10']:.4f}  NDCG@10 {r['ndcg_at_10']:.4f}")
    print("selected:", selection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
