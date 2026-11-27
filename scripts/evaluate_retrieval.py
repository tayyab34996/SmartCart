"""Evaluate TF-IDF and MiniLM retrieval on the dev queries (Phase 7).

Usage:
    python scripts/evaluate_retrieval.py --select   # apply the selection rules, freeze the choices in the config
    python scripts/evaluate_retrieval.py            # evaluate with the frozen choices and write the outputs
    python scripts/evaluate_retrieval.py --check    # rebuild the outputs in memory and compare with the committed files

Only ``data/benchmarks/retrieval_dev.json`` is read. The test queries are evaluated once,
in Phase 11, with the frozen ``configs/retrieval.json``. Every product-text variant is
scored with both methods; the product text and the candidate count are chosen by the
rules written in the config. Outputs:
- ``results/metrics/retrieval_dev.json``: every variant x method, the selection, the
  Recall@k curve, results by query type, and the pipeline-pool diagnostic;
- ``results/predictions/retrieval_dev_{tfidf,minilm}.jsonl``: per-query rankings
  (selected product text);
- ``results/predictions/retrieval_benchmark_results.json``: the headline dev table;
- figure ``11_retrieval_tfidf_vs_minilm.png`` (drawn from the metrics; not part of ``--check``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch  # noqa: E402

from smartcart.data.contracts import load_catalog  # noqa: E402
from smartcart.retrieval.api import retrieve_candidates  # noqa: E402
from smartcart.retrieval.benchmark import (  # noqa: E402
    evaluate, load_queries, select_candidate_count, select_product_text,
)
from smartcart.retrieval.index import MODEL_NAME, MODEL_REVISION  # noqa: E402

FIGURE_11 = "results/figures/11_retrieval_tfidf_vs_minilm.png"
HEADLINE = ("recall_at_5", "recall_at_10", "mrr", "num_queries")


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n"


def jsonl_text(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)


def pipeline_pool(catalog: dict, ingredients: list[str], methods: list[str], product_text: str,
                  grid: list[int]) -> dict:
    """Diagnostic for Phase 9: with the pipeline query (the canonical ingredient name), how
    often does the top k hold *every* available product of that ingredient?"""
    out = {}
    for method in methods:
        complete = {}
        for k in grid:
            hits = 0
            for ing in ingredients:
                wanted = {p["id"] for p in catalog["products"] if p["ingredient_id"] == ing and p["available"]}
                ranked = retrieve_candidates(ing, catalog, method=method, top_k=k, product_text=product_text)
                pool = {c["product_id"] for c in ranked}
                hits += wanted <= pool
            complete[str(k)] = round(hits / len(ingredients), 6)
        out[method] = complete
    return {"query": "canonical ingredient name (as in retrieve_candidates)",
            "ingredients": len(ingredients), "share_with_every_product_in_top_k": out}


def build(config: dict) -> tuple[dict, dict, dict]:
    if config["evaluated_splits"] != ["dev"]:
        raise SystemExit("Phase 7 evaluates dev only; the test split is for Phase 11")
    catalog = load_catalog(ROOT / config["data"]["catalog"])
    queries = load_queries(ROOT / config["data"]["retrieval_dev"], "dev")
    methods = config["methods"]
    grid = config["candidate_count"]["grid"]
    variants = config["product_text"]["candidates"] + config["product_text"]["diagnostic_only"]
    results = {v: {m: evaluate(queries, catalog, m, v, grid) for m in methods} for v in variants}
    text = select_product_text(results, config["product_text"]["candidates"], methods)
    curve = results[text][config["candidate_count"]["method"]]["summary"]["recall_at_k"]
    k = select_candidate_count(curve, grid)
    selection = {"product_text": text, "candidate_count": k}
    dev_ingredients = sorted({q["required_ingredient"] for q in queries})
    metrics = {
        "split": "dev", "num_queries": len(queries), "model": MODEL_NAME, "revision": MODEL_REVISION,
        "selection": {
            "product_text": {"rule": config["product_text"]["selection"], "selected": text,
                             "table": {v: {m: {key: results[v][m]["summary"][key] for key in HEADLINE}
                                           for m in methods}
                                       for v in variants},
                             "diagnostic_only": config["product_text"]["diagnostic_only"]},
            "candidate_count": {"rule": config["candidate_count"]["selection"], "selected": k,
                                "recall_at_k": {m: results[text][m]["summary"]["recall_at_k"] for m in methods}},
        },
        "results": {m: results[text][m]["summary"] for m in methods},
        "pipeline_pool": pipeline_pool(catalog, dev_ingredients, methods, text, grid),
    }
    outputs = config["outputs"]
    files = {outputs["metrics"]: json_text(metrics)}
    for m in methods:
        files[outputs["predictions"].format(method=m)] = jsonl_text(results[text][m]["rows"])
    files[outputs["benchmark_results"]] = json_text({
        "split_evaluated": "dev", "product_text": text, "candidate_count": k,
        "dev": {m: {key: results[text][m]["summary"][key] for key in HEADLINE} for m in methods},
        "test": "not evaluated in Phase 7; evaluated once in Phase 11 with configs/retrieval.json frozen",
    })
    return files, metrics, selection


def figure(metrics: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    methods = [("tfidf", "TF-IDF"), ("minilm", "MiniLM")]
    res = metrics["results"]
    types = list(res["minilm"]["by_query_type"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    keys = [("recall_at_5", "Recall@5"), ("recall_at_10", "Recall@10"), ("mrr", "MRR")]
    x = np.arange(len(keys))
    for j, (m, label) in enumerate(methods):
        vals = [res[m][k] for k, _ in keys]
        bars = axes[0].bar(x + (j - 0.5) * 0.38, vals, 0.38, label=label)
        axes[0].bar_label(bars, fmt="%.2f", fontsize=8)
    axes[0].set_xticks(x, [k for _, k in keys])
    axes[0].set_ylim(0, 1.08)
    axes[0].set_title(f"All {metrics['num_queries']} dev queries", fontsize=10)
    axes[0].legend(fontsize=8)
    xt = np.arange(len(types))
    for j, (m, label) in enumerate(methods):
        vals = [res[m]["by_query_type"][t]["recall_at_10"] for t in types]
        bars = axes[1].bar(xt + (j - 0.5) * 0.38, vals, 0.38, label=label)
        axes[1].bar_label(bars, fmt="%.2f", fontsize=7)
    counts = [res["minilm"]["by_query_type"][t]["num_queries"] for t in types]
    axes[1].set_xticks(xt, [f"{t}\n(n={n})" for t, n in zip(types, counts)], fontsize=8)
    axes[1].set_ylim(0, 1.08)
    axes[1].set_title("Recall@10 by query type", fontsize=10)
    curves = metrics["selection"]["candidate_count"]["recall_at_k"]
    for m, label in methods:
        ks = [int(k) for k in curves[m]]
        axes[2].plot(ks, list(curves[m].values()), marker="o", label=label)
    k_sel = metrics["selection"]["candidate_count"]["selected"]
    axes[2].axvline(k_sel, color="grey", linestyle="--", linewidth=1)
    axes[2].text(k_sel, 0.05, f" k = {k_sel}", fontsize=8)
    axes[2].set_ylim(0, 1.05)
    axes[2].set_xlabel("candidates retrieved (k)")
    axes[2].set_title("Recall@k (candidate count chosen on dev)", fontsize=10)
    axes[2].legend(fontsize=8)
    text = metrics["selection"]["product_text"]["selected"]
    fig.suptitle(f"Retrieval on the dev queries (product text: {text}; simulated catalog of 466 products)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(ROOT / FIGURE_11, dpi=150, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/retrieval.json")
    ap.add_argument("--select", action="store_true", help="freeze the selected product text and candidate count")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config_path = ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    torch.set_num_threads(config["model"]["torch_threads"])
    files, metrics, selection = build(config)
    frozen = {"product_text": config["product_text"]["selected"],
              "candidate_count": config["candidate_count"]["selected"]}
    if args.select:
        config["product_text"]["selected"] = selection["product_text"]
        config["candidate_count"]["selected"] = selection["candidate_count"]
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                               newline="\n")
        print("frozen selection:", selection)
    elif selection != frozen:
        raise SystemExit(f"selection {selection} differs from the frozen config {frozen}; run --select on purpose")
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    figure(metrics)
    for m in config["methods"]:
        r = metrics["results"][m]
        print(f"{m:7s} R@5 {r['recall_at_5']:.3f}  R@10 {r['recall_at_10']:.3f}  MRR {r['mrr']:.3f}")
    print("selected:", selection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
