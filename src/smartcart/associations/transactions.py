"""Ingredient-level Track B transactions (Phase 8).

An order's transaction is the set of catalog ingredients its Instacart products map to
(``data/processed/instacart_ingredient_map.csv``, Phase 3). Unmapped products are
dropped; an order with no mapped product is an empty transaction that still counts in
the support denominator and in a user's number of orders.

Only the splits that are asked for are read: the order IDs come from the Track B
manifest, and rows of any other order are skipped while streaming the basket file, so
Phase 8 never loads the contents of a test order.
"""

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

SPLITS = ("train", "validation", "test")


@dataclass
class TrackB:
    """Transactions per order plus each user's orders by split."""

    items: list[str]                                         # the ingredient universe, sorted
    orders: dict[int, frozenset[str]] = field(default_factory=dict)
    user_orders: dict[int, dict[str, list[int]]] = field(default_factory=dict)

    def split_orders(self, split: str) -> list[int]:
        return [o for u in sorted(self.user_orders) for o in self.user_orders[u].get(split, [])]


def load_mapping(path: Path) -> dict[int, str]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return {int(r["instacart_product_id"]): r["ingredient_id"] for r in csv.DictReader(handle)
                if r["ingredient_id"]}


def load_manifest(path: Path, splits: tuple[str, ...]) -> dict[int, dict[str, list[int]]]:
    unknown = set(splits) - set(SPLITS)
    if unknown:
        raise ValueError(f"unknown Track B split(s) {sorted(unknown)}")
    users = json.loads(Path(path).read_text(encoding="utf-8"))["users"]
    out = {}
    for user, record in users.items():
        out[int(user)] = {}
        for split in splits:
            ids = record[split]
            out[int(user)][split] = [int(o) for o in (ids if isinstance(ids, list) else [ids])]
    return out


def load_trackb(catalog: dict, manifest: Path, mapping: Path, baskets: Path,
                splits: tuple[str, ...] = ("train", "validation")) -> TrackB:
    """Ingredient transactions for the requested splits only."""
    user_orders = load_manifest(manifest, splits)
    wanted = {o for record in user_orders.values() for ids in record.values() for o in ids}
    product_to_ingredient = load_mapping(mapping)
    contents: dict[int, set[str]] = {o: set() for o in wanted}
    with gzip.open(baskets, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            order = int(row["order_id"])
            if order not in wanted:
                continue
            ingredient = product_to_ingredient.get(int(row["product_id"]))
            if ingredient is not None:
                contents[order].add(ingredient)
    items = sorted(i["id"] for i in catalog["ingredients"])
    unknown = {i for s in contents.values() for i in s} - set(items)
    if unknown:
        raise ValueError(f"mapped ingredients missing from the catalog: {sorted(unknown)}")
    return TrackB(items=items, orders={o: frozenset(s) for o, s in contents.items()}, user_orders=user_orders)
