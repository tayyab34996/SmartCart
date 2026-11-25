"""Instacart transaction sample, Track B split and ingredient mapping (Phase 3, D2).

The raw archive is streamed in place. Only order IDs, product IDs and order order
are used: ``add_to_cart_order`` and ``reordered`` are not quantities and are dropped,
and each basket is a set of distinct products.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path

import pandas as pd

USABLE_EVAL_SETS = ("prior", "train")  # "test" orders have no product rows in the archive


def user_rank_key(seed: int, user_id: int) -> str:
    """Deterministic, library-independent sampling key for one user."""
    return hashlib.sha256(f"{seed}:{int(user_id)}".encode("ascii")).hexdigest()


def select_users(eligible_user_ids, seed: int, n_users: int) -> list[int]:
    """Return the ``n_users`` eligible users with the smallest hash keys, sorted by ID."""
    ranked = sorted((user_rank_key(seed, uid), int(uid)) for uid in eligible_user_ids)
    if len(ranked) < n_users:
        raise ValueError(f"only {len(ranked)} eligible users, {n_users} requested")
    return sorted(uid for _, uid in ranked[:n_users])


def track_b_split(order_ids_in_sequence: list[int]) -> dict:
    """Final usable order is test, the one before it validation, the rest training."""
    if len(order_ids_in_sequence) < 3:
        raise ValueError("a Track B split needs at least three usable orders")
    ids = [int(o) for o in order_ids_in_sequence]
    return {"train": ids[:-2], "validation": ids[-2], "test": ids[-1]}


def read_orders(archive: zipfile.ZipFile) -> pd.DataFrame:
    with archive.open("orders.csv") as handle:
        return pd.read_csv(handle, usecols=["order_id", "user_id", "eval_set", "order_number"],
                           dtype={"order_id": "int32", "user_id": "int32", "eval_set": "category",
                                  "order_number": "int16"})


def usable_orders_by_user(orders: pd.DataFrame) -> pd.DataFrame:
    """Orders that carry product rows, sorted by user and order number."""
    usable = orders[orders["eval_set"].isin(USABLE_EVAL_SETS)]
    return usable.sort_values(["user_id", "order_number"], kind="mergesort").reset_index(drop=True)


def read_order_products(archive: zipfile.ZipFile, member: str, order_ids: set[int],
                        chunksize: int) -> tuple[pd.DataFrame, dict]:
    """Stream one order-products member in chunks and keep rows of the given orders."""
    kept, rows_read, chunks = [], 0, 0
    wanted = pd.Index(sorted(order_ids), dtype="int32")
    with archive.open(member) as handle:
        reader = pd.read_csv(handle, usecols=["order_id", "product_id"],
                             dtype={"order_id": "int32", "product_id": "int32"}, chunksize=chunksize)
        for chunk in reader:
            rows_read += len(chunk)
            chunks += 1
            kept.append(chunk[chunk["order_id"].isin(wanted)])
    frame = pd.concat(kept, ignore_index=True)
    before = len(frame)
    frame = frame.drop_duplicates()
    return frame, {"member": member, "rows_read": rows_read, "chunks": chunks,
                   "rows_kept": before, "duplicate_rows_dropped": before - len(frame)}


def read_products(archive: zipfile.ZipFile) -> pd.DataFrame:
    with archive.open("products.csv") as handle:
        products = pd.read_csv(handle, dtype={"product_id": "int32", "aisle_id": "int16",
                                              "department_id": "int16"}, keep_default_na=False)
    for member, key, label in (("aisles.csv", "aisle_id", "aisle"),
                               ("departments.csv", "department_id", "department")):
        with archive.open(member) as handle:
            lookup = pd.read_csv(handle, keep_default_na=False)
        products = products.merge(lookup.astype({key: "int16"}), on=key, how="left")
    return products


# --- ingredient mapping -------------------------------------------------------------

def read_mapping_rules(path: Path) -> list[dict]:
    """Rules in file order; the first rule that matches a product wins."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if not row["ingredient_id"].startswith("#")]
    rules = []
    for index, row in enumerate(rows):
        aisles = {int(a) for a in row["aisle_ids"].split("|") if a}
        if not aisles or not row["include"]:
            raise ValueError(f"rule {index} for {row['ingredient_id']} needs aisle_ids and include")
        rules.append({
            "rule_id": f"r{index:03d}",
            "ingredient_id": row["ingredient_id"],
            "aisle_ids": aisles,
            "include": re.compile(row["include"]),
            "exclude": re.compile(row["exclude"]) if row["exclude"] else None,
            "include_text": row["include"],
            "exclude_text": row["exclude"],
        })
    return rules


def normalise_name(name: str) -> str:
    return " ".join(name.lower().replace("&", " and ").split())


def match_product(name: str, aisle_id: int, rules: list[dict]) -> tuple[dict | None, list[str]]:
    """Return the winning rule and the IDs of every rule that matched."""
    text = normalise_name(name)
    hits = [rule for rule in rules if aisle_id in rule["aisle_ids"] and rule["include"].search(text)
            and not (rule["exclude"] and rule["exclude"].search(text))]
    return (hits[0] if hits else None), [h["rule_id"] for h in hits]


def map_products(products: pd.DataFrame, rules: list[dict], catalog_ingredients: set[str]) -> list[dict]:
    unknown = {r["ingredient_id"] for r in rules} - catalog_ingredients
    if unknown:
        raise ValueError(f"mapping rules name unknown ingredients: {sorted(unknown)}")
    mapped = []
    for row in products.itertuples(index=False):
        winner, hits = match_product(row.product_name, int(row.aisle_id), rules)
        if winner is None:
            continue
        other = sorted({r["ingredient_id"] for r in rules if r["rule_id"] in hits} - {winner["ingredient_id"]})
        mapped.append({
            "instacart_product_id": int(row.product_id),
            "product_name": row.product_name,
            "aisle": row.aisle,
            "ingredient_id": winner["ingredient_id"],
            "rule_id": winner["rule_id"],
            "other_matching_ingredients": "|".join(other),
            "mapping_status": "rule_matched",
        })
    return sorted(mapped, key=lambda m: m["instacart_product_id"])


def review_order(product_ids, salt: str) -> list[int]:
    """Deterministic review-sampling order (hash of salt and product ID)."""
    return sorted((int(p) for p in product_ids),
                  key=lambda p: hashlib.sha256(f"{salt}:{p}".encode("ascii")).hexdigest())


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        raise ValueError("empty sample")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return round(centre - margin, 4), round(centre + margin, 4)


def evaluate_review(review: list[dict], mapping: list[dict], unmapped_in_rule_aisles: set[int],
                    sample_size: int) -> dict:
    """Score the committed manual review and confirm it matches the current mapping."""
    mapped = {m["instacart_product_id"]: m["ingredient_id"] for m in mapping}
    precision = [r for r in review if r["review_set"] == "precision_heldout"]
    recall = [r for r in review if r["review_set"] == "recall_unmapped"]
    expected_p = review_order(mapped, "heldout")[:sample_size]
    expected_r = review_order(unmapped_in_rule_aisles, "recall")[:sample_size]
    same_sample = ([int(r["instacart_product_id"]) for r in precision] == expected_p
                   and [int(r["instacart_product_id"]) for r in recall] == expected_r
                   and all(mapped[int(r["instacart_product_id"])] == r["mapped_ingredient_id"] for r in precision))
    correct = sum(r["judgement"] == "correct" for r in precision)
    missed = sum(r["judgement"] == "missed" for r in recall)
    miss_rate = missed / len(recall)
    est_true_mapped = len(mapped) * correct / len(precision)
    est_missed = len(unmapped_in_rule_aisles) * miss_rate
    return {
        "review_matches_current_mapping": same_sample,
        "precision_sample": len(precision),
        "precision_correct": correct,
        "precision": round(correct / len(precision), 4),
        "precision_wilson_95": wilson_interval(correct, len(precision)),
        "recall_sample_unmapped": len(recall),
        "recall_sample_missed": missed,
        "unmapped_miss_rate": round(miss_rate, 4),
        "unmapped_miss_rate_wilson_95": wilson_interval(missed, len(recall)),
        "estimated_product_recall_in_rule_aisles": round(est_true_mapped / (est_true_mapped + est_missed), 4),
        "note": "single reviewer (the build agent); rules were frozen before the held-out samples were drawn; "
                "recall covers only aisles named by a rule",
    }


def open_archive(path: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(path)


def csv_text(rows: list[dict], fields: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
