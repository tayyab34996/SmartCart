"""Retrieval interface (BUILD_PHASES section 4.3).

``retrieve_candidates`` ranks the **whole catalog** for one required ingredient and
returns the top ``k`` product IDs with a score in [0, 1] and a rank. Retrieval never
enforces hard rules (ingredient identity, unit, availability, diet); the selector does.

The query is the ingredient's canonical name (catalog ``name`` without parentheses).
``search_products`` ranks the catalog for free text (the retrieval benchmark).

Methods: ``tfidf`` (word 1–2-gram TF-IDF, Phase 5) and ``minilm`` (frozen MiniLM +
exact FAISS inner-product index, Phase 7). Both index the same product text, chosen on
dev data in Phase 7 (``DEFAULT_PRODUCT_TEXT``, frozen in ``configs/retrieval.json``).
E0 keeps the Phase 1 ``legacy`` text so its committed results still reproduce.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from smartcart.nlu.lexicon import clean_name
from smartcart.retrieval.index import MiniLMIndex, TfidfIndex, rank
from smartcart.retrieval.product_text import VARIANTS, catalog_texts, normalize_text

METHODS = ("tfidf", "minilm")
DEFAULT_PRODUCT_TEXT = "display_name_ingredient"  # frozen on dev in Phase 7 (configs/retrieval.json)
INDEX_CACHE_DIR = Path(__file__).resolve().parents[3] / "models" / "retrieval"
_INDEX_CACHE: dict[tuple[str, str, str], object] = {}


def catalog_fingerprint(catalog: dict) -> str:
    rows = [(p["id"], p["name"], p["ingredient_id"]) for p in catalog["products"]]
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def ingredient_query(ingredient_id: str, catalog: dict) -> str:
    for ingredient in catalog["ingredients"]:
        if ingredient["id"] == ingredient_id:
            return clean_name(ingredient["name"])
    raise KeyError(f"unknown ingredient {ingredient_id}")


def index_cache_name(method: str, product_text: str) -> str:
    return f"{method}_{product_text}"


def get_index(catalog: dict, method: str = "tfidf", product_text: str | None = None):
    """The (process-cached) index for ``method`` over ``product_text``. A MiniLM index is
    read from ``models/retrieval/`` when its input hash matches, else built in memory."""
    if method not in METHODS:
        raise ValueError(f"unknown retrieval method {method}")
    variant = product_text or DEFAULT_PRODUCT_TEXT
    if variant not in VARIANTS:
        raise ValueError(f"unknown product text variant {variant}")
    key = (method, variant, catalog_fingerprint(catalog))
    if key not in _INDEX_CACHE:
        ids = [p["id"] for p in catalog["products"]]
        texts = catalog_texts(catalog, variant)
        if method == "tfidf":
            _INDEX_CACHE[key] = TfidfIndex(ids, texts)
        else:
            cached = MiniLMIndex.load_cached(INDEX_CACHE_DIR, index_cache_name(method, variant), ids, texts)
            _INDEX_CACHE[key] = cached if cached is not None else MiniLMIndex(ids, texts)
    return _INDEX_CACHE[key]


def search_products(query: str, catalog: dict, method: str = "tfidf", top_k: int | None = 10,
                    product_text: str | None = None) -> list[dict]:
    """Rank the whole catalog for free text; ``top_k=None`` returns every product."""
    if top_k is not None and top_k <= 0:
        raise ValueError("top_k must be positive")
    index = get_index(catalog, method, product_text)
    ranked = rank(index.scores(normalize_text(query)), index.product_ids, top_k)
    return [{"product_id": index.product_ids[i], "retrieval_score": score, "rank": r}
            for r, (i, score) in enumerate(ranked, start=1)]


def retrieve_candidates(ingredient_id: str, catalog: dict, method: str = "tfidf", top_k: int = 10,
                        product_text: str | None = None) -> list[dict]:
    if method not in METHODS:
        raise ValueError(f"unknown retrieval method {method}")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    variant = product_text or DEFAULT_PRODUCT_TEXT
    query = ingredient_query(ingredient_id, catalog)
    if variant == "legacy":  # E0's Phase 1 behaviour: the raw lower-cased query
        index = get_index(catalog, method, variant)
        ranked = rank(index.scores(query.strip().lower()), index.product_ids, top_k, round_before_sort=False)
        return [{"product_id": index.product_ids[i], "retrieval_score": score, "rank": r}
                for r, (i, score) in enumerate(ranked, start=1)]
    return search_products(query, catalog, method=method, top_k=top_k, product_text=variant)
