"""Retrieval indexes over product text (Phase 7): TF-IDF and frozen MiniLM + FAISS.

Both indexes score **every** catalog product for a query; ``rank`` orders them by the
reported score (rounded to 6 decimals, so tiny float differences between machines
cannot reorder near-ties) and then by product ID. Retrieval never applies hard rules.

MiniLM (``sentence-transformers/all-MiniLM-L6-v2``, pinned revision) is used frozen:
product texts are encoded once in catalog order with a fixed batch size, L2-normalized,
and stored in an exact inner-product index (``faiss.IndexFlatIP``), so the inner
product is the cosine similarity. A query is always encoded on its own (batch of one),
so ``retrieve_candidates`` and the benchmark see identical query vectors.

The MiniLM index can be cached on disk (``scripts/build_index.py``) together with the
SHA-256 of its inputs (model, revision, product IDs and texts). A cache whose input
hash does not match is ignored and the index is rebuilt in memory.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
ENCODE_BATCH_SIZE = 64
SCORE_DECIMALS = 6
_ENCODERS: dict[tuple[str, str], object] = {}


def load_encoder(model_name: str = MODEL_NAME, revision: str = MODEL_REVISION):
    """The frozen sentence encoder, loaded once per process from the local cache."""
    key = (model_name, revision)
    if key not in _ENCODERS:
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(model_name, revision=revision, local_files_only=True, device="cpu")
        encoder.eval()
        _ENCODERS[key] = encoder
    return _ENCODERS[key]


def encode_texts(texts: list[str], encoder, batch_size: int = ENCODE_BATCH_SIZE) -> np.ndarray:
    """L2-normalized float32 embeddings, one row per text."""
    vectors = encoder.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                             convert_to_numpy=True, show_progress_bar=False)
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    import faiss

    faiss.normalize_L2(vectors)
    return vectors


def input_hash(product_ids: list[str], texts: list[str], model_name: str = MODEL_NAME,
               revision: str = MODEL_REVISION, batch_size: int = ENCODE_BATCH_SIZE) -> str:
    payload = {"model": model_name, "revision": revision, "batch_size": batch_size,
               "products": [[pid, text] for pid, text in zip(product_ids, texts)]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def rank(scores: np.ndarray, product_ids: list[str], top_k: int | None = None,
         round_before_sort: bool = True) -> list[tuple[int, float]]:
    """(product index, rounded score) for the whole catalog, best first; ties by product ID.

    ``round_before_sort=False`` sorts on the raw float score, the Phase 1 TF-IDF order that
    E0 depends on: there, scores that are equal in theory can differ in the last bits and
    are ordered by that float noise rather than by product ID.
    """
    rounded = [round(float(s), SCORE_DECIMALS) for s in scores]
    keys = rounded if round_before_sort else [float(s) for s in scores]
    order = sorted(range(len(product_ids)), key=lambda i: (-keys[i], product_ids[i]))
    if top_k is not None:
        order = order[:top_k]
    return [(i, rounded[i]) for i in order]


class TfidfIndex:
    """Word 1–2-gram TF-IDF with cosine similarity (the Phase 1 settings)."""

    method = "tfidf"

    def __init__(self, product_ids: list[str], texts: list[str]):
        self.product_ids = list(product_ids)
        self.texts = list(texts)
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), lowercase=True)
        self.matrix = self.vectorizer.fit_transform(self.texts)

    def scores(self, query: str) -> np.ndarray:
        """Cosine similarity of non-negative TF-IDF vectors, already in [0, 1]."""
        if not query.strip():
            return np.zeros(len(self.product_ids))
        sims = cosine_similarity(self.vectorizer.transform([query.strip().lower()]), self.matrix)[0]
        return np.clip(sims, 0.0, 1.0)


class MiniLMIndex:
    """Frozen MiniLM embeddings in an exact FAISS inner-product index.

    ``scores`` maps the cosine similarity ``s`` in [-1, 1] to ``(1 + s) / 2`` in [0, 1],
    which keeps the order and satisfies the retrieval contract.
    """

    method = "minilm"

    def __init__(self, product_ids: list[str], texts: list[str], encoder=None, index=None):
        import faiss

        self.product_ids = list(product_ids)
        self.texts = list(texts)
        self.encoder = encoder if encoder is not None else load_encoder()
        self.input_hash = input_hash(self.product_ids, self.texts)
        if index is None:
            vectors = encode_texts(self.texts, self.encoder)
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
        if index.ntotal != len(self.product_ids):
            raise ValueError("index size does not match the catalog")
        self.index = index

    def embed_query(self, query: str) -> np.ndarray:
        return encode_texts([query.strip().lower()], self.encoder, batch_size=1)

    def scores(self, query: str) -> np.ndarray:
        if not query.strip():
            return np.full(len(self.product_ids), 0.5)
        sims, idx = self.index.search(self.embed_query(query), self.index.ntotal)
        cosine = np.empty(len(self.product_ids), dtype=np.float64)
        cosine[idx[0]] = sims[0]
        return np.clip((1.0 + cosine) / 2.0, 0.0, 1.0)

    # ----- on-disk cache -------------------------------------------------------------
    def save(self, directory: Path, name: str, meta: dict | None = None) -> tuple[Path, Path]:
        import faiss

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        index_path, meta_path = directory / f"{name}.faiss", directory / f"{name}.json"
        faiss.write_index(self.index, str(index_path))
        record = {"input_hash": self.input_hash, "model": MODEL_NAME, "revision": MODEL_REVISION,
                  "batch_size": ENCODE_BATCH_SIZE, "products": len(self.product_ids),
                  "dimension": self.index.d, **(meta or {})}
        meta_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
        return index_path, meta_path

    @classmethod
    def load_cached(cls, directory: Path, name: str, product_ids: list[str], texts: list[str], encoder=None):
        """The cached index if its input hash matches ``product_ids`` and ``texts``, else None."""
        import faiss

        index_path, meta_path = Path(directory) / f"{name}.faiss", Path(directory) / f"{name}.json"
        if not index_path.is_file() or not meta_path.is_file():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("input_hash") != input_hash(product_ids, texts):
            return None
        return cls(product_ids, texts, encoder=encoder, index=faiss.read_index(str(index_path)))
