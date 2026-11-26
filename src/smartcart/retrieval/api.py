"""Retrieval interface (BUILD_PHASES section 4.3).

``retrieve_candidates`` ranks the **whole catalog** for one required ingredient and
returns the top ``k`` product IDs with a score in [0, 1] and a rank. Retrieval never
enforces hard rules (ingredient identity, unit, availability, diet); the selector does.

The query is the ingredient's canonical name (catalog ``name`` without parentheses).
Only ``method="tfidf"`` exists so far; MiniLM is added in Phase 7.
"""

from __future__ import annotations

import hashlib
import json

from smartcart.nlu.lexicon import clean_name
from smartcart.retrieval.tfidf import build_tfidf_retriever, search_products_tfidf

METHODS = ("tfidf", "minilm")
_INDEX_CACHE: dict[tuple[str, str], tuple] = {}


def catalog_fingerprint(catalog: dict) -> str:
    rows = [(p["id"], p["name"], p["ingredient_id"]) for p in catalog["products"]]
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def ingredient_query(ingredient_id: str, catalog: dict) -> str:
    for ingredient in catalog["ingredients"]:
        if ingredient["id"] == ingredient_id:
            return clean_name(ingredient["name"])
    raise KeyError(f"unknown ingredient {ingredient_id}")


def _index(catalog: dict, method: str) -> tuple:
    key = (method, catalog_fingerprint(catalog))
    if key not in _INDEX_CACHE:
        if method == "tfidf":
            _INDEX_CACHE[key] = build_tfidf_retriever(catalog["products"])
        else:
            raise NotImplementedError("MiniLM retrieval is implemented in Phase 7")
    return _INDEX_CACHE[key]


def retrieve_candidates(ingredient_id: str, catalog: dict, method: str = "tfidf", top_k: int = 10) -> list[dict]:
    if method not in METHODS:
        raise ValueError(f"unknown retrieval method {method}")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    state = _index(catalog, method)
    query = ingredient_query(ingredient_id, catalog)
    ranked = search_products_tfidf(query, state, top_k=top_k)
    # Cosine similarity of non-negative TF-IDF vectors is already in [0, 1].
    return [{"product_id": p["id"], "retrieval_score": round(min(1.0, max(0.0, p["retrieval_score"])), 6),
             "rank": rank} for rank, p in enumerate(ranked, start=1)]
