"""Instacart user sample, Track B split manifest and ingredient mapping (Phase 3, D2).

Usage:  .venv\\Scripts\\python scripts\\prepare_transactions.py [--config configs/instacart_sample.json] [--check]

--check rebuilds the user sample, split manifest and mapping in memory and fails if
the committed files differ (reproducibility check). It does not read order products.
"""

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from smartcart.data.instacart import (  # noqa: E402
    USABLE_EVAL_SETS, csv_text, evaluate_review, map_products, open_archive, read_mapping_rules,
    read_order_products, read_orders, read_products, select_users, track_b_split, usable_orders_by_user,
)

# The tracked mapping holds IDs only; Instacart product names are written to an ignored
# interim copy because the competition data is not redistributed.
MAPPING_FIELDS = ["instacart_product_id", "ingredient_id", "rule_id", "other_matching_ingredients", "mapping_status"]
READABLE_FIELDS = ["instacart_product_id", "product_name", "aisle", "ingredient_id", "rule_id",
                   "other_matching_ingredients", "mapping_status"]


class Profiler:
    def __init__(self):
        self.start = time.perf_counter()
        self.steps = []
        try:
            import psutil
            self.process = psutil.Process()
        except ImportError:  # psutil is pinned in requirements-lock.txt; tolerate its absence
            self.process = None

    def mark(self, step: str) -> None:
        rss = self.process.memory_info().rss / 2**20 if self.process else None
        self.steps.append({"step": step, "elapsed_s": round(time.perf_counter() - self.start, 1),
                           "rss_mb": None if rss is None else round(rss, 1)})
        print(f"[{self.steps[-1]['elapsed_s']:>6}s] {step}", flush=True)

    def summary(self) -> dict:
        peaks = [s["rss_mb"] for s in self.steps if s["rss_mb"] is not None]
        return {"steps": self.steps, "peak_rss_mb_at_steps": max(peaks) if peaks else None,
                "note": "RSS sampled after each step (psutil); not a continuous peak measurement"}


def dump(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def stats(series: pd.Series) -> dict:
    return {"min": int(series.min()), "median": float(series.median()), "mean": round(float(series.mean()), 2),
            "max": int(series.max())}


def build_manifests(orders: pd.DataFrame, config: dict) -> tuple[dict, dict, dict]:
    """Return the users manifest, the Track B manifest and eligibility counts."""
    usable = usable_orders_by_user(orders)
    per_user = usable.groupby("user_id").size()
    minimum = config["min_usable_orders"]
    eligible = per_user[per_user >= minimum].index
    users = select_users(eligible.tolist(), config["seed"], config["n_users"])
    id_text = ",".join(map(str, users))
    sampling = {
        "method": "sha256(f'{seed}:{user_id}') ascending; first n_users eligible users; stored sorted by ID",
        "seed": config["seed"],
        "n_users": config["n_users"],
        "eligibility": f"at least {minimum} usable orders; usable = eval_set in {list(USABLE_EVAL_SETS)}",
    }
    users_manifest = {**sampling, "eligible_users": int(len(eligible)),
                      "user_ids_sha256": hashlib.sha256(id_text.encode("ascii")).hexdigest(), "user_ids": users}
    chosen = usable[usable["user_id"].isin(users)]
    splits = {str(uid): track_b_split(group["order_id"].tolist())
              for uid, group in chosen.groupby("user_id", sort=True)}
    trackb = {
        "policy": "per user, usable orders by order_number: last = test, second-to-last = validation, "
                  "earlier = train",
        "basket_semantics": "set of distinct product_ids; add_to_cart_order and reordered are not used",
        "seed": config["seed"],
        "users_manifest": config["outputs"]["users"],
        "n_users": len(splits),
        "users": splits,
    }
    total_users = int(orders["user_id"].nunique())
    eligibility = {
        "users_in_archive": total_users,
        "users_with_usable_orders": int(len(per_user)),
        "eligible_users": int(len(eligible)),
        "excluded_users_fewer_than_min_usable_orders": int((per_user < minimum).sum()),
        "orders_in_archive": int(len(orders)),
        "orders_excluded_no_product_rows": {k: int(v) for k, v in
                                            orders[~orders["eval_set"].isin(USABLE_EVAL_SETS)]
                                            .groupby("eval_set", observed=True).size().items()},
        "usable_orders_per_user_all": stats(per_user),
        "usable_orders_per_sampled_user": stats(per_user[per_user.index.isin(users)]),
    }
    return users_manifest, trackb, eligibility


def trackb_text(trackb: dict) -> str:
    """One user per line keeps the 10k-user manifest small and diffable."""
    head = {k: v for k, v in trackb.items() if k != "users"}
    lines = [json.dumps(head, ensure_ascii=False)[:-1] + ', "users": {']
    items = list(trackb["users"].items())
    for index, (uid, split) in enumerate(items):
        comma = "," if index < len(items) - 1 else ""
        lines.append(f"  {json.dumps(uid)}: {json.dumps(split, separators=(',', ':'))}{comma}")
    lines.append("}}")
    return "\n".join(lines) + "\n"


def build_mapping(archive, config: dict) -> tuple[pd.DataFrame, list[dict], dict]:
    catalog = json.loads((ROOT / config["catalog"]).read_text(encoding="utf-8"))
    ingredients = {i["id"] for i in catalog["ingredients"]}
    rules = read_mapping_rules(ROOT / config["mapping_rules"])
    products = read_products(archive)
    mapping = map_products(products, rules, ingredients)
    context = {"catalog": catalog, "rules": rules, "ingredients": ingredients, "review": None}
    review_path = ROOT / config["mapping_review"]
    if review_path.is_file():
        with review_path.open(encoding="utf-8", newline="") as handle:
            review = list(csv.DictReader(handle))
        rule_aisles = set().union(*(r["aisle_ids"] for r in rules))
        mapped = {m["instacart_product_id"] for m in mapping}
        unmapped = {int(p) for p, a in zip(products["product_id"], products["aisle_id"])
                    if int(a) in rule_aisles and int(p) not in mapped}
        context["review"] = evaluate_review(review, mapping, unmapped, config["review_sample_size"])
    return products, mapping, context


def mapping_checks(mapping: list[dict], context: dict, baskets: pd.DataFrame, labels: pd.Series) -> dict:
    catalog, rules = context["catalog"], context["rules"]
    used = {line["ingredient_id"] for r in catalog["recipes"] for line in r["ingredients"]}
    frame = pd.DataFrame(mapping)
    by_ingredient = frame.groupby("ingredient_id").size()
    product_to_ing = frame.set_index("instacart_product_id")["ingredient_id"]
    rows = baskets.assign(ingredient_id=baskets["product_id"].map(product_to_ing), split=labels)
    mapped_rows = rows["ingredient_id"].notna()
    orders_with_mapped = rows[mapped_rows].groupby("split")["order_id"].nunique()
    orders_total = rows.groupby("split")["order_id"].nunique()
    rule_hits = frame.groupby("rule_id").size()
    return {
        "rules": len(rules),
        "rules_with_no_match": [r["rule_id"] for r in rules if r["rule_id"] not in rule_hits.index],
        "instacart_products_mapped": len(frame),
        "products_matched_by_more_than_one_ingredient": int((frame["other_matching_ingredients"] != "").sum()),
        "catalog_ingredients_with_mapping": int(len(by_ingredient)),
        "catalog_ingredients": len(context["ingredients"]),
        "recipe_ingredients_with_mapping": len(used & set(by_ingredient.index)),
        "recipe_ingredients": len(used),
        "ingredients_without_mapping": sorted(context["ingredients"] - set(by_ingredient.index)),
        "sample_item_rows_mapped_share": round(float(mapped_rows.mean()), 4),
        "sample_orders_with_mapped_item_share": {s: round(float(orders_with_mapped.get(s, 0) / n), 4)
                                                 for s, n in orders_total.items()},
        "products_per_ingredient": {k: int(v) for k, v in by_ingredient.sort_index().items()},
        "manual_review": context.get("review"),
        "catalog_product_matches": 0,
        "catalog_product_match_note": "catalog products are simulated house-brand options, so no Instacart "
                                      "product is a verified match; every catalog external_ids stays {}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/instacart_sample.json"))
    parser.add_argument("--check", action="store_true", help="verify committed manifests are reproducible")
    args = parser.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    out = {k: ROOT / v for k, v in config["outputs"].items()}
    profiler = Profiler()
    archive = open_archive(ROOT / config["archive"])
    orders = read_orders(archive)
    profiler.mark(f"read orders.csv ({len(orders):,} rows)")
    users_manifest, trackb, eligibility = build_manifests(orders, config)
    profiler.mark("selected users and built Track B split")
    products, mapping, context = build_mapping(archive, config)
    profiler.mark(f"mapped products ({len(mapping):,} of {len(products):,})")
    tracked_mapping = [{k: m[k] for k in MAPPING_FIELDS} for m in mapping]
    expected = {"users": dump(users_manifest), "trackb": trackb_text(trackb),
                "mapping": csv_text(tracked_mapping, MAPPING_FIELDS)}
    if args.check:
        same = {k: out[k].is_file() and out[k].read_text(encoding="utf-8") == text for k, text in expected.items()}
        print("reproducible:", same)
        return 0 if all(same.values()) else 1

    label_of = {}
    for split in trackb["users"].values():
        label_of.update({o: "train" for o in split["train"]})
        label_of[split["validation"]] = "validation"
        label_of[split["test"]] = "test"
    order_ids = set(label_of)
    parts, reads = [], []
    for member in ("order_products__prior.csv", "order_products__train.csv"):
        frame, info = read_order_products(archive, member, order_ids, config["chunksize"])
        parts.append(frame)
        reads.append(info)
        profiler.mark(f"streamed {member} ({info['rows_read']:,} rows, {info['chunks']} chunks)")
    baskets = pd.concat(parts, ignore_index=True)
    meta = orders.set_index("order_id").loc[baskets["order_id"].unique(), ["user_id", "order_number"]]
    baskets = baskets.merge(meta, left_on="order_id", right_index=True)
    baskets = baskets.sort_values(["user_id", "order_number", "product_id"], kind="mergesort")
    baskets = baskets[["user_id", "order_id", "order_number", "product_id"]].reset_index(drop=True)
    labels = baskets["order_id"].map(label_of)
    missing_orders = order_ids - set(baskets["order_id"].unique())
    sizes = baskets.groupby("order_id").size()
    split_of_order = pd.Series(label_of)

    for key in ("users", "trackb", "mapping", "mapping_readable", "baskets", "checks"):
        out[key].parent.mkdir(parents=True, exist_ok=True)
    for key, text in expected.items():
        out[key].write_text(text, encoding="utf-8", newline="\n")
    out["mapping_readable"].write_text(csv_text(mapping, READABLE_FIELDS), encoding="utf-8", newline="\n")
    baskets.to_csv(out["baskets"], index=False, compression={"method": "gzip", "mtime": 0})
    profiler.mark("wrote outputs")

    checks = {
        "eligibility": eligibility,
        "sample": {"seed": config["seed"], "n_users": users_manifest["n_users"],
                   "user_ids_sha256": users_manifest["user_ids_sha256"]},
        "trackb": {
            "orders": {s: int((split_of_order == s).sum()) for s in ("train", "validation", "test")},
            "train_orders_per_user": stats(pd.Series([len(v["train"]) for v in trackb["users"].values()])),
            "items_per_basket": {s: stats(sizes[sizes.index.isin(split_of_order[split_of_order == s].index)])
                                 for s in ("train", "validation", "test")},
            "item_rows": int(len(baskets)),
            "distinct_products": int(baskets["product_id"].nunique()),
            "split_orders_without_product_rows": len(missing_orders),
            "test_orders_from_instacart_train_set": int(orders.set_index("order_id").loc[
                [v["test"] for v in trackb["users"].values()], "eval_set"].eq("train").sum()),
        },
        "order_product_reads": reads,
        "mapping": mapping_checks(mapping, context, baskets, labels),
        "profile": profiler.summary(),
    }
    checks["checks"] = {
        "sample_size_met": users_manifest["n_users"] == config["n_users"],
        "every_sampled_user_has_min_usable_orders":
            checks["eligibility"]["usable_orders_per_sampled_user"]["min"] >= config["min_usable_orders"],
        "every_split_order_has_items": not missing_orders,
        "no_duplicate_items_in_basket": all(r["duplicate_rows_dropped"] == 0 for r in reads),
        "every_recipe_ingredient_mapped":
            checks["mapping"]["recipe_ingredients_with_mapping"] == checks["mapping"]["recipe_ingredients"],
        "manual_review_matches_current_mapping": bool(context["review"])
            and context["review"]["review_matches_current_mapping"],
    }
    checks["all_checks_pass"] = all(checks["checks"].values())
    out["checks"].write_text(dump(checks), encoding="utf-8", newline="\n")
    print(json.dumps({"checks": checks["checks"], "trackb": checks["trackb"]["orders"],
                      "mapping": {k: checks["mapping"][k] for k in
                                  ("instacart_products_mapped", "recipe_ingredients_with_mapping",
                                   "ingredients_without_mapping", "sample_item_rows_mapped_share")}}, indent=2))
    return 0 if checks["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
