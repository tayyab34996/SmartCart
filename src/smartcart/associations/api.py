"""Association interface (BUILD_PHASES section 4.3), Phase 8.

- ``pair_score(a, b) -> float in [0, 1]``: symmetric, 0.0 when unknown. ``a`` and ``b``
  may be catalog product IDs or ingredient IDs; products are scored through their
  ingredient, because the rules are ingredient-level (no catalog product has an
  Instacart ID). Two items of the same ingredient score 0.0 (not a pair).
- ``basket_pair_score(items)``: the mean pair score over all pairs, in [0, 1]. Use this
  in an objective; never sum an unbounded number of pair scores.
- ``history_score(user_id, item) -> float in [0, 1]``: the share of the user's Track B
  training orders that contain the item's ingredient; 0.0 for unknown users or items.

Pair scores come from the committed ``data/processed/rules.csv`` (thresholds frozen in
``configs/associations.json``). History scores are computed from the ignored
``data/interim/instacart/`` files (rebuild them with ``scripts/prepare_transactions.py``).
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from itertools import combinations
from pathlib import Path

from smartcart.associations.mining import lift_to_score

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "configs" / "associations.json"


@lru_cache(maxsize=1)
def _config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _product_ingredients() -> dict[str, str]:
    catalog = json.loads((ROOT / _config()["data"]["catalog"]).read_text(encoding="utf-8"))
    out = {i["id"]: i["id"] for i in catalog["ingredients"]}
    out.update({p["id"]: p["ingredient_id"] for p in catalog["products"]})
    return out


@lru_cache(maxsize=1)
def _pairs() -> dict[tuple[str, str], float]:
    path = ROOT / _config()["outputs"]["rules"]
    pairs = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            if int(r["length"]) == 2:
                a, b = sorted((r["antecedent"], r["consequent"]))
                pairs[(a, b)] = lift_to_score(float(r["lift"]))
    return pairs


@lru_cache(maxsize=1)
def _history() -> dict[int, dict[str, float]]:
    from smartcart.associations.transactions import load_trackb

    d = _config()["data"]
    catalog = json.loads((ROOT / d["catalog"]).read_text(encoding="utf-8"))
    baskets = ROOT / d["baskets"]
    if not baskets.is_file():
        raise FileNotFoundError(f"{baskets} is missing: run scripts/prepare_transactions.py first")
    trackb = load_trackb(catalog, ROOT / d["trackb"], ROOT / d["mapping"], baskets, splits=("train",))
    history = {}
    for user, record in trackb.user_orders.items():
        orders = record["train"]
        counts: dict[str, int] = {}
        for o in orders:
            for item in trackb.orders[o]:
                counts[item] = counts.get(item, 0) + 1
        history[user] = {item: c / len(orders) for item, c in counts.items()}
    return history


def ingredient_of(item: str) -> str | None:
    return _product_ingredients().get(item)


def pair_score(a: str, b: str) -> float:
    ia, ib = ingredient_of(a), ingredient_of(b)
    if ia is None or ib is None or ia == ib:
        return 0.0
    return _pairs().get((ia, ib) if ia < ib else (ib, ia), 0.0)


def basket_pair_score(items: list[str]) -> float:
    pairs = list(combinations(items, 2))
    return sum(pair_score(a, b) for a, b in pairs) / len(pairs) if pairs else 0.0


def history_score(user_id, item: str) -> float:
    if user_id is None:
        return 0.0
    ingredient = ingredient_of(item)
    if ingredient is None:
        return 0.0
    return _history().get(int(user_id), {}).get(ingredient, 0.0)
