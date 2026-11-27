"""Build and cache the MiniLM + FAISS product index (Phase 7).

Usage:
    python scripts/build_index.py            # encode the catalog, write the index cache and the manifest
    python scripts/build_index.py --check    # rebuild in memory; compare the manifest and any local cache

The product text is the one frozen in ``configs/retrieval.json``. The index goes to the
git-ignored ``models/retrieval/minilm_<text>.faiss`` with a JSON record of its input hash
(model, revision, batch size, product IDs and texts). ``retrieve_candidates`` reads the
cache only when the hash matches the current catalog, and otherwise builds the index in
memory, so a stale cache can never be used. The committed manifest
``results/metrics/retrieval_index.json`` records what the index was built from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import faiss  # noqa: E402
import torch  # noqa: E402

from smartcart.data.contracts import load_catalog  # noqa: E402
from smartcart.retrieval.api import index_cache_name  # noqa: E402
from smartcart.retrieval.index import ENCODE_BATCH_SIZE, MODEL_NAME, MODEL_REVISION, MiniLMIndex  # noqa: E402
from smartcart.retrieval.product_text import catalog_texts  # noqa: E402


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def manifest(config: dict, index: MiniLMIndex, product_text: str) -> dict:
    catalog_bytes = (ROOT / config["data"]["catalog"]).read_bytes().replace(b"\r\n", b"\n")
    return {
        "model": MODEL_NAME, "revision": MODEL_REVISION, "batch_size": ENCODE_BATCH_SIZE,
        "index": "faiss.IndexFlatIP", "dimension": index.index.d, "normalized": True,
        "product_text": product_text, "products": len(index.product_ids),
        "catalog": config["data"]["catalog"],
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "input_hash": index.input_hash,
        "cache": f"{config['index_cache']}/{index_cache_name('minilm', product_text)}.faiss (git-ignored)",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/retrieval.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    if config["model"]["name"] != MODEL_NAME or config["model"]["revision"] != MODEL_REVISION:
        raise SystemExit("the config's model or revision differs from smartcart.retrieval.index")
    product_text = config["product_text"]["selected"]
    if not product_text:
        raise SystemExit("no product text is frozen yet; run scripts/evaluate_retrieval.py --select first")
    torch.set_num_threads(config["model"]["torch_threads"])
    catalog = load_catalog(ROOT / config["data"]["catalog"])
    ids = [p["id"] for p in catalog["products"]]
    index = MiniLMIndex(ids, catalog_texts(catalog, product_text))
    record = manifest(config, index, product_text)
    manifest_path = ROOT / config["outputs"]["index_manifest"]
    cache_dir, name = ROOT / config["index_cache"], index_cache_name("minilm", product_text)
    if args.check:
        ok = manifest_path.exists() and manifest_path.read_text(encoding="utf-8") == json_text(record)
        print(("same    " if ok else "DIFFERS ") + config["outputs"]["index_manifest"])
        cache_path = cache_dir / f"{name}.faiss"
        if cache_path.exists():
            cached = MiniLMIndex.load_cached(cache_dir, name, ids, index.texts, encoder=index.encoder)
            same = cached is not None and bytes(faiss.serialize_index(cached.index)) == bytes(
                faiss.serialize_index(index.index))
            ok = ok and same
            print(("same    " if same else "DIFFERS ") + f"{config['index_cache']}/{name}.faiss (local cache)")
        else:
            print(f"no local cache at {config['index_cache']}/{name}.faiss (run without --check to build it)")
        return 0 if ok else 1
    index.save(cache_dir, name, meta={"product_text": product_text})
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json_text(record), encoding="utf-8", newline="\n")
    print(f"indexed {record['products']} products ({product_text}), dimension {record['dimension']}")
    print(f"cache: {config['index_cache']}/{name}.faiss; input hash {record['input_hash'][:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
