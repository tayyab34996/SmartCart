"""Retrieval benchmark scoring on the locked query files (Phase 7).

For each query the whole catalog is ranked from the query text, then only request-side
constraints are applied (required unit, dietary rules, availability; the corrected
``filter_eligible_candidates``). The gold ``required_ingredient`` defines relevance only:
it is never passed to the filter, which would leak the answer (the Phase 1 defect).
"""

from __future__ import annotations

import json
from pathlib import Path

from smartcart.retrieval.api import search_products
from smartcart.retrieval.filtering import filter_eligible_candidates

MRR_CUTOFF = 10


def load_queries(path: Path, split: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("benchmark") != "retrieval" or data.get("split") != split:
        raise ValueError(f"{path} is not the retrieval {split} split")
    return data["queries"]


def filtered_ranking(query: dict, catalog: dict, method: str, product_text: str) -> list[dict]:
    """The whole-catalog ranking after the request-side filter, best first."""
    products = {p["id"]: p for p in catalog["products"]}
    ranked = search_products(query["query"], catalog, method=method, top_k=None, product_text=product_text)
    candidates = [{**products[r["product_id"]], "retrieval_score": r["retrieval_score"]} for r in ranked]
    return filter_eligible_candidates(candidates, required_unit=query.get("required_unit"),
                                      dietary_rules=query.get("dietary_rules") or None)


def query_metrics(ranked_ids: list[str], relevant: set[str], ks: list[int]) -> dict:
    first = next((i for i, pid in enumerate(ranked_ids, start=1) if pid in relevant), None)
    recall = {k: (len(set(ranked_ids[:k]) & relevant) / len(relevant) if relevant else 0.0) for k in ks}
    rr = 1.0 / first if first is not None and first <= MRR_CUTOFF else 0.0
    return {"first_relevant_rank": first, "recall": recall, "reciprocal_rank": rr}


def evaluate(queries: list[dict], catalog: dict, method: str, product_text: str, ks: list[int]) -> dict:
    """Per-query rows and mean metrics (overall and by query type)."""
    ks = sorted(set(ks) | {5, 10})
    rows = []
    for q in queries:
        ranking = filtered_ranking(q, catalog, method, product_text)
        ids = [c["id"] for c in ranking]
        m = query_metrics(ids, set(q["relevant_ids"]), ks)
        rows.append({
            "query_id": q["query_id"], "query": q["query"], "query_type": q["query_type"],
            "required_ingredient": q["required_ingredient"], "relevant_ids": q["relevant_ids"],
            "top10": [[c["id"], c["retrieval_score"]] for c in ranking[:10]],
            "top1_ingredient": ranking[0]["ingredient_id"] if ranking else None,
            "first_relevant_rank": m["first_relevant_rank"],
            "recall_at_5": round(m["recall"][5], 6), "recall_at_10": round(m["recall"][10], 6),
            "reciprocal_rank": round(m["reciprocal_rank"], 6),
            "recall_at_k": {str(k): round(v, 6) for k, v in m["recall"].items()},
        })
    return {"rows": rows, "summary": summarize(rows, ks)}


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def summarize(rows: list[dict], ks: list[int]) -> dict:
    def block(subset: list[dict]) -> dict:
        return {"num_queries": len(subset),
                "recall_at_5": _mean([r["recall_at_5"] for r in subset]),
                "recall_at_10": _mean([r["recall_at_10"] for r in subset]),
                "mrr": _mean([r["reciprocal_rank"] for r in subset]),
                "top1_correct_ingredient": sum(r["top1_ingredient"] == r["required_ingredient"] for r in subset),
                "no_relevant_in_top10": sum(r["recall_at_10"] == 0 for r in subset)}

    types = sorted({r["query_type"] for r in rows})
    return {**block(rows),
            "recall_at_k": {str(k): _mean([r["recall_at_k"][str(k)] for r in rows]) for k in ks},
            "by_query_type": {t: block([r for r in rows if r["query_type"] == t]) for t in types}}


def select_product_text(results: dict, candidates: list[str], methods: list[str]) -> str:
    """Highest Recall@10 averaged over the methods; then averaged MRR; then candidate order."""
    def key(variant: str) -> tuple:
        r10 = sum(results[variant][m]["summary"]["recall_at_10"] for m in methods) / len(methods)
        mrr = sum(results[variant][m]["summary"]["mrr"] for m in methods) / len(methods)
        return (-round(r10, 6), -round(mrr, 6), candidates.index(variant))
    return min(candidates, key=key)


def select_candidate_count(recall_at_k: dict, grid: list[int], tolerance: float = 0.01) -> int:
    """Smallest k whose Recall@k is within ``tolerance`` of Recall@k at the largest k."""
    best = recall_at_k[str(max(grid))]
    return min(k for k in grid if recall_at_k[str(k)] >= round(best - tolerance, 6))
