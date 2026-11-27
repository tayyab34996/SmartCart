"""Mine ingredient-level FP-Growth rules on Track B training orders (Phase 8).

Usage:
    python scripts/mine_rules.py            # mine, export the rules, measure the selection activity
    python scripts/mine_rules.py --check    # rebuild the committed outputs in memory and compare

Needs the thresholds frozen by ``scripts/evaluate_trackb.py --select``. Only training
orders are read. Outputs:
- ``data/processed/rules.csv``: antecedent, consequent, length, count, support,
  confidence, lift, for the rules that pass the frozen thresholds;
- ``results/metrics/association_rules.json``: transaction counts, itemsets by length,
  the strongest pairs and triples, and the most frequent ingredients;
- ``results/metrics/association_selection_activity.json``: whether the pair and history
  terms can change product selection on the dev basket scenarios;
- ``results/metrics/association_mining_profile.json``: time and memory (machine-dependent,
  not part of ``--check``);
- figure ``12_association_rules.png`` (not part of ``--check``).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import psutil  # noqa: E402

from smartcart.associations.activity import measure  # noqa: E402
from smartcart.associations.mining import (  # noqa: E402
    filter_rules, lift_to_score, mine_itemsets, mine_rules, one_hot, pair_table, passes,
)
from smartcart.associations.transactions import load_trackb  # noqa: E402
from smartcart.data.contracts import load_catalog  # noqa: E402

FIGURE_12 = "results/figures/12_association_rules.png"
FIELDS = ["antecedent", "consequent", "length", "count", "support", "confidence", "lift"]


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def csv_text(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: r[k] for k in FIELDS} for r in rows)
    return buffer.getvalue()


def rss_mb() -> float:
    return round(psutil.Process().memory_info().rss / 1e6, 1)


def build(config: dict) -> tuple[dict, dict, dict]:
    selected = config["selection"]["selected"]
    if not selected:
        raise SystemExit("no thresholds are frozen yet; run scripts/evaluate_trackb.py --select first")
    d = config["data"]
    catalog = load_catalog(ROOT / d["catalog"])
    profile = {"steps": []}
    t0 = time.perf_counter()
    trackb = load_trackb(catalog, ROOT / d["trackb"], ROOT / d["mapping"], ROOT / d["baskets"], splits=("train",))
    profile["steps"].append({"step": "load training transactions", "seconds": round(time.perf_counter() - t0, 2),
                             "rss_mb": rss_mb()})
    train = [trackb.orders[o] for o in trackb.split_orders("train")]
    frame = one_hot(train, trackb.items)
    floor, max_len = config["mining"]["min_count_floor"], config["mining"]["max_len"]
    by_len = {}
    for length in range(2, max_len + 1):
        t0 = time.perf_counter()
        itemsets = mine_itemsets(frame, floor, length)
        rules = mine_rules(itemsets, len(frame))
        profile["steps"].append({"step": f"fpgrowth + rules, max_len={length}, min_count={floor}",
                                 "seconds": round(time.perf_counter() - t0, 2), "rss_mb": rss_mb(),
                                 "itemsets": len(itemsets), "rules": len(rules)})
        by_len[length] = itemsets["itemsets"].map(len).value_counts().sort_index().to_dict()
    min_count, min_conf = selected["min_count"], selected["min_confidence"]
    kept = filter_rules(rules, min_count, min_conf)
    pairs = pair_table(rules)
    scored = sorted(((a, b, e) for (a, b), e in pairs.items() if passes(e, min_count, min_conf) and e["lift"] > 1),
                    key=lambda x: (-x[2]["lift"], x[0], x[1]))
    item_counts = {i: int(frame[i].sum()) for i in trackb.items}
    n = len(frame)

    def pair_row(a, b, e):
        return {"pair": [a, b], "count": e["count"], "lift": e["lift"], "pair_score": lift_to_score(e["lift"]),
                "confidence": {f"{a}->{b}": e.get("confidence_ab", 0.0), f"{b}->{a}": e.get("confidence_ba", 0.0)}}

    triples = sorted((r for r in kept if r["length"] == 3),
                     key=lambda r: (-r["lift"], r["antecedent"], r["consequent"]))
    summary = {
        "level": config["level"], "transactions": n, "nonempty_transactions": int(frame.any(axis=1).sum()),
        "items_seen": int(sum(c > 0 for c in item_counts.values())), "items_in_catalog": len(trackb.items),
        "mined": {"min_count_floor": floor, "max_len": max_len, "itemsets_by_length": by_len[max_len],
                  "rules": len(rules)},
        "thresholds": {"min_count": min_count, "min_confidence": min_conf},
        "exported_rules": {"total": len(kept), "pairs (both directions)": sum(r["length"] == 2 for r in kept),
                           "triples": sum(r["length"] == 3 for r in kept)},
        "pairs_with_positive_score": len(scored),
        "pairs_passing_with_lift_at_most_1": sum(1 for e in pairs.values() if passes(e, min_count, min_conf)
                                                 and e["lift"] <= 1),
        "top_pairs_by_lift": [pair_row(a, b, e) for a, b, e in scored[:20]],
        "top_pairs_by_count": [pair_row(a, b, e) for a, b, e in sorted(scored, key=lambda x: (-x[2]["count"],
                                                                                              x[0], x[1]))[:20]],
        "top_triples_by_lift": triples[:10],
        "top_items_by_share_of_orders": [{"ingredient_id": i, "orders": c, "share": round(c / n, 6)}
                                         for i, c in sorted(item_counts.items(), key=lambda x: (-x[1], x[0]))[:20]],
    }

    # Selection activity, with the in-memory scores (identical to smartcart.associations.api).
    ingredient_of = {i["id"]: i["id"] for i in catalog["ingredients"]}
    ingredient_of.update({p["id"]: p["ingredient_id"] for p in catalog["products"]})
    score = {(a, b): lift_to_score(e["lift"]) for (a, b), e in pairs.items() if passes(e, min_count, min_conf)}

    def pair_fn(x, y):
        a, b = ingredient_of[x], ingredient_of[y]
        return 0.0 if a == b else score.get((a, b) if a < b else (b, a), 0.0)

    history = {}
    for user, record in trackb.user_orders.items():
        counts = {}
        for o in record["train"]:
            for item in trackb.orders[o]:
                counts[item] = counts.get(item, 0) + 1
        history[user] = {i: c / len(record["train"]) for i, c in counts.items()}

    def history_fn(user, x):
        return history.get(int(user), {}).get(ingredient_of[x], 0.0)

    scenarios = json.loads((ROOT / d["basket_dev"]).read_text(encoding="utf-8"))["scenarios"]
    activity = measure(scenarios, catalog, pair_fn, history_fn)
    activity = {"split": "basket_dev", "thresholds": summary["thresholds"], **activity}

    out = config["outputs"]
    files = {out["rules"]: csv_text(kept), out["rules_summary"]: json_text(summary),
             out["selection_activity"]: json_text(activity)}
    return files, {"summary": summary, "item_counts": item_counts, "scored": scored}, profile


def figure(data: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = data["summary"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    top = summary["top_items_by_share_of_orders"]
    axes[0].barh([t["ingredient_id"] for t in top][::-1], [t["share"] for t in top][::-1], color="#4C78A8")
    axes[0].set_xlabel("share of training orders containing the ingredient")
    axes[0].set_title(f"Most frequent ingredients ({summary['transactions']:,} training orders)", fontsize=10)
    pairs = summary["top_pairs_by_lift"][:15]
    axes[1].barh([f"{p['pair'][0]} + {p['pair'][1]} (n={p['count']})" for p in pairs][::-1],
                 [p["lift"] for p in pairs][::-1], color="#F58518")
    axes[1].set_xlabel("lift")
    t = summary["thresholds"]
    axes[1].set_title(f"Strongest pairs (count >= {t['min_count']}, confidence >= {t['min_confidence']})",
                      fontsize=10)
    for ax in axes:
        ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(ROOT / FIGURE_12, dpi=150, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/associations.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    files, data, profile = build(config)
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    profile["peak_rss_mb"] = max(s["rss_mb"] for s in profile["steps"])
    profile["note"] = "machine-dependent; not part of --check"
    (ROOT / config["outputs"]["mining_profile"]).write_text(json_text(profile), encoding="utf-8", newline="\n")
    figure(data)
    s = data["summary"]
    print(f"exported {s['exported_rules']['total']} rules; {s['pairs_with_positive_score']} pairs score > 0")
    for step in profile["steps"]:
        print(step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
