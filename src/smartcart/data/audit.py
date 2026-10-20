"""Stream the original SmartCart ZIP files without extracting or modifying them."""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import io
import json
import math
import re
import time
import zipfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
from pathlib import Path


MISSING = {"", "NA", "NULL"}
VECTOR_TOKEN = re.compile(r'\s*("(?:[^"\\]|\\.)*"|NA|NULL)\s*')
EVAL_CODES = {"prior": 1, "train": 2, "test": 3}
MAX_ORDER_ID = 50_000_000


def parse_r_vector(value: str) -> list[str | None]:
    """Parse only quoted strings and missing markers; never execute R or Python."""
    value = value.strip()
    if value in MISSING or value in {"character(0)", "numeric(0)"}:
        return []
    if value.startswith("c(") and value.endswith(")"):
        value = value[2:-1].strip()
    if not value:
        return []
    result = []
    position = 0
    while position < len(value):
        match = VECTOR_TOKEN.match(value, position)
        if match is None:
            raise ValueError("Unsupported R vector syntax")
        token = match.group(1)
        # Preserve R string escapes as text. Vector structure, not unescaping,
        # determines alignment; commas inside quoted ingredient names stay intact.
        result.append(token[1:-1] if token.startswith('"') else None)
        position = match.end()
        if position == len(value):
            break
        if value[position] != ",":
            raise ValueError("Expected a vector separator")
        position += 1
        if not value[position:].strip():
            raise ValueError("Trailing vector separator")
    return result


@lru_cache(maxsize=8192)
def positive_amount(value: str | None) -> bool:
    if value is None:
        return False
    try:
        pieces = value.strip().split()
        if len(pieces) not in (1, 2):
            return False
        numbers = [Fraction(piece) for piece in pieces]
        if len(pieces) == 2 and (numbers[0].denominator != 1 or "/" not in pieces[1] or not 0 <= numbers[1] < 1):
            return False
        return all(number >= 0 for number in numbers) and sum(numbers) > 0
    except (ValueError, ZeroDivisionError):
        return False


@lru_cache(maxsize=1024)
def positive_number(value: str) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except ValueError:
        return False


@contextmanager
def csv_rows(archive: zipfile.ZipFile, member: str, required: set[str]):
    with archive.open(member) as binary:
        with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames or []
            if len(columns) != len(set(columns)):
                raise ValueError(f"Duplicate columns in {member}")
            if missing := required - set(columns):
                raise ValueError(f"{member} is missing columns: {sorted(missing)}")

            def checked_rows():
                for row in reader:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError(f"Malformed CSV record in {member} at line {reader.line_num}")
                    yield row

            yield columns, checked_rows()


def archive_manifest(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    with zipfile.ZipFile(path) as archive:
        return {
            "path": path.as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
            "members": [
                {"name": item.filename, "bytes": item.file_size,
                 "compressed_bytes": item.compress_size, "zip_crc32": f"{item.CRC:08x}"}
                for item in archive.infolist()
            ],
        }


def audit_lookup(archive: zipfile.ZipFile, member: str, key: str, label: str):
    ids, counts = set(), Counter()
    with csv_rows(archive, member, {key, label}) as (columns, rows):
        for row in rows:
            identifier = int(row[key])
            counts["rows"] += 1
            counts["duplicate_ids"] += identifier in ids
            counts["blank_names"] += not row[label].strip()
            ids.add(identifier)
    return ids, {"columns": columns, **dict(counts)}


def audit_instacart(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        aisles, aisle_stats = audit_lookup(archive, "aisles.csv", "aisle_id", "aisle")
        departments, department_stats = audit_lookup(
            archive, "departments.csv", "department_id", "department")
        products, product_names, products_stats = set(), set(), Counter()
        with csv_rows(archive, "products.csv", {
            "product_id", "product_name", "aisle_id", "department_id"
        }) as (columns, rows):
            for row in rows:
                identifier, name = int(row["product_id"]), row["product_name"].strip()
                products_stats["rows"] += 1
                products_stats["duplicate_ids"] += identifier in products
                products_stats["duplicate_names"] += name in product_names
                products_stats["blank_names"] += not name
                products_stats["unknown_aisle_ids"] += int(row["aisle_id"]) not in aisles
                products_stats["unknown_department_ids"] += int(row["department_id"]) not in departments
                products.add(identifier)
                product_names.add(name)
        product_stats = {"columns": columns, **dict(products_stats)}
        print(f"Instacart products: {products_stats['rows']:,}", flush=True)

        # Dense order IDs in this release allow a small byte lookup instead of
        # holding millions of Python dictionaries or joining each transaction.
        order_types = bytearray(1)
        order_stats, eval_counts, user_counts = Counter(), Counter(), Counter()
        with csv_rows(archive, "orders.csv", {
            "order_id", "user_id", "eval_set", "order_number", "order_dow",
            "order_hour_of_day", "days_since_prior_order"
        }) as (columns, rows):
            for row in rows:
                identifier = int(row["order_id"])
                if not 0 < identifier <= MAX_ORDER_ID:
                    raise ValueError(f"Order ID exceeds the documented audit limit: {identifier}")
                if identifier >= len(order_types):
                    order_types.extend(b"\x00" * (identifier + 1 - len(order_types)))
                order_stats["rows"] += 1
                order_stats["duplicate_ids"] += order_types[identifier] != 0
                order_types[identifier] = EVAL_CODES.get(row["eval_set"], 4)
                eval_counts[row["eval_set"]] += 1
                user_counts[int(row["user_id"])] += 1
                order_stats["unknown_eval_set"] += row["eval_set"] not in EVAL_CODES
                order_stats["invalid_order_number"] += int(row["order_number"]) < 1
                order_stats["invalid_day"] += not 0 <= int(row["order_dow"]) <= 6
                order_stats["invalid_hour"] += not 0 <= int(row["order_hour_of_day"]) <= 23
                day_gap = row["days_since_prior_order"]
                if not day_gap:
                    order_stats["missing_days_since_prior_order"] += 1
                    order_stats["missing_gap_after_first_order"] += int(row["order_number"]) != 1
                else:
                    order_stats["invalid_gap"] += not 0 <= float(day_gap) <= 30
        orders = {"columns": columns, **dict(order_stats), "users": len(user_counts),
                  "eval_set_counts": dict(eval_counts),
                  "orders_per_user_histogram": dict(sorted(Counter(user_counts.values()).items()))}
        print(f"Instacart orders: {order_stats['rows']:,}", flush=True)

        lines = {}
        for split in ("prior", "train"):
            member = f"order_products__{split}.csv"
            stats, basket_sizes = Counter(), Counter()
            seen_orders = bytearray(len(order_types))
            previous_order, basket_products, basket_positions = None, set(), set()
            basket_rows = 0

            def finish_basket():
                if basket_rows:
                    basket_sizes[basket_rows] += 1
                    stats["groups_with_noncontiguous_cart_positions"] += (
                        basket_positions != set(range(1, basket_rows + 1)))

            print(f"Reading {member}...", flush=True)
            with csv_rows(archive, member, {
                "order_id", "product_id", "add_to_cart_order", "reordered"
            }) as (columns, rows):
                for row in rows:
                    order_id, product_id = int(row["order_id"]), int(row["product_id"])
                    position = int(row["add_to_cart_order"])
                    if order_id != previous_order:
                        finish_basket()
                        if 0 < order_id < len(seen_orders):
                            stats["fragmented_order_groups"] += seen_orders[order_id] != 0
                            stats["unique_order_ids"] += seen_orders[order_id] == 0
                            seen_orders[order_id] = 1
                        previous_order, basket_rows = order_id, 0
                        basket_products, basket_positions = set(), set()
                    stats["rows"] += 1
                    basket_rows += 1
                    stats["unknown_product_ids"] += product_id not in products
                    known_order = 0 < order_id < len(order_types) and order_types[order_id] != 0
                    stats["unknown_order_ids"] += not known_order
                    stats["wrong_eval_set"] += known_order and order_types[order_id] != EVAL_CODES[split]
                    stats["duplicate_products_within_contiguous_order_group"] += product_id in basket_products
                    stats["duplicate_cart_positions_within_contiguous_order_group"] += position in basket_positions
                    stats["invalid_reordered_flags"] += row["reordered"] not in {"0", "1"}
                    stats["invalid_cart_positions"] += position < 1
                    basket_products.add(product_id)
                    basket_positions.add(position)
                    if stats["rows"] % 5_000_000 == 0:
                        print(f"{member}: {stats['rows']:,} rows read...", flush=True)
            finish_basket()
            stats["orders_missing_product_rows"] = sum(
                code == EVAL_CODES[split] and not seen_orders[index]
                for index, code in enumerate(order_types))
            lines[split] = {"columns": columns, **dict(stats),
                            "global_pair_duplicate_check_complete": stats["fragmented_order_groups"] == 0,
                            "basket_size_histogram": dict(sorted(basket_sizes.items()))}
            print(f"{member}: {stats['rows']:,} rows", flush=True)
    return {"aisles": aisle_stats, "departments": department_stats,
            "products": product_stats, "orders": orders, "order_products": lines,
            "limitations": ["No product prices, purchased quantities, barcodes, or dietary evidence.",
                            "User/order-sequence pair uniqueness and historical label correctness were not checked."]}


def audit_foodcom(path: Path, shortlist_size: int = 50) -> tuple[dict, list[dict]]:
    stats, categories, ingredient_counts = Counter(), Counter(), Counter()
    recipe_ids, shortlist = set(), []
    required = {"RecipeId", "Name", "RecipeCategory", "RecipeIngredientParts",
                "RecipeIngredientQuantities", "RecipeServings"}
    with zipfile.ZipFile(path) as archive:
        with csv_rows(archive, "recipes.csv", required) as (columns, rows):
            for row in rows:
                stats["rows"] += 1
                recipe_id = int(row["RecipeId"])
                duplicate_recipe = recipe_id in recipe_ids
                stats["duplicate_ids"] += duplicate_recipe
                recipe_ids.add(recipe_id)
                stats["blank_names"] += not row["Name"].strip()
                servings_valid = positive_number(row["RecipeServings"])
                stats["missing_or_invalid_servings"] += not servings_valid
                categories[row["RecipeCategory"]] += 1
                try:
                    ingredients = parse_r_vector(row["RecipeIngredientParts"])
                    quantities = parse_r_vector(row["RecipeIngredientQuantities"])
                except ValueError:
                    stats["unsupported_vector_syntax_rows"] += 1
                    continue
                ingredient_counts[len(ingredients)] += 1
                aligned = bool(ingredients) and len(ingredients) == len(quantities)
                stats["empty_ingredient_lists"] += not ingredients
                stats["ingredient_quantity_length_mismatches"] += len(ingredients) != len(quantities)
                stats["aligned_nonempty_rows"] += aligned
                amounts_valid = bool(quantities) and all(positive_amount(q) for q in quantities)
                names_valid = bool(ingredients) and all(i and i.strip() for i in ingredients)
                stats["rows_with_missing_ingredient_names"] += any(not i or not i.strip() for i in ingredients)
                stats["rows_with_missing_quantity_entries"] += any(q is None or not q.strip() for q in quantities)
                stats["rows_with_nonpositive_or_unparsed_amounts"] += not amounts_valid
                structurally_usable = aligned and servings_valid and amounts_valid and names_valid
                stats["structurally_usable_before_unit_review"] += structurally_usable
                searchable = f"{row['Name']} {row['RecipeCategory']}".lower()
                meal_terms = ("rice", "pasta", "lentil", "chickpea", "chicken", "curry", "potato")
                if not duplicate_recipe and structurally_usable and 4 <= len(ingredients) <= 12 and any(
                    word in searchable for word in meal_terms
                ):
                    stats["meal_shortlist_candidates_before_unit_review"] += 1
                    candidate = {
                        "source_recipe_id": recipe_id, "name": row["Name"],
                        "category": row["RecipeCategory"], "source_servings": row["RecipeServings"],
                        "ingredient_count": len(ingredients),
                        "ingredient_names_json": json.dumps(ingredients, ensure_ascii=False),
                        "source_amounts_json": json.dumps(quantities, ensure_ascii=False),
                        "unit_review_status": "unverified",
                        "review_status": "needs_manual_review", "optimizer_ready": False,
                    }
                    # Keep at most N records; smaller ingredient lists and IDs win.
                    entry = (-len(ingredients), -recipe_id, candidate)
                    if len(shortlist) < shortlist_size:
                        heapq.heappush(shortlist, entry)
                    elif entry[:2] > shortlist[0][:2]:
                        heapq.heapreplace(shortlist, entry)
                if stats["rows"] % 100_000 == 0:
                    print(f"Food.com recipes read: {stats['rows']:,}", flush=True)
    candidates = [item[2] for item in sorted(shortlist, key=lambda x: (-x[0], -x[1]))]
    return {"columns": columns, **dict(stats),
            "has_dedicated_ingredient_unit_column": any("unit" in col.lower() for col in columns),
            "ingredient_count_histogram": dict(sorted(ingredient_counts.items())),
            "top_categories": dict(categories.most_common(20)),
            "shortlist_count": len(candidates),
            "shortlist_policy": "Meal-keyword candidates with 4–12 ingredients; rank by ingredient count then recipe ID; units unverified.",
            "limitations": ["No ingredient units were inferred or validated; optimizer-ready recipe count is not established.",
                            "CSV list strings were structurally parsed, not executed; R escapes remain preserved.",
                            "Review CSV and both Parquet members were inventoried but not scanned."]}, candidates


def write_report(summary: dict, path: Path) -> None:
    instacart, recipes = summary["instacart"], summary["foodcom"]
    orders, lines = instacart["orders"], instacart["order_products"]
    report = [
        "# SmartCart initial data audit", "", f"Generated: {summary['created_at_utc']}", "",
        "This report describes source data, not model performance. Raw archives were read in place and not modified.", "",
        "## Acquired archives", "", "| Archive | Bytes | SHA-256 |", "| --- | ---: | --- |",
    ]
    for archive, key in zip(summary["archives"], ("instacart_archive", "foodcom_archive")):
        report.append(f"| `{summary['config'][key]}` | {archive['bytes']:,} | `{archive['sha256']}` |")
    report.extend([
        "", "## Instacart", "", "| Table | Rows |", "| --- | ---: |",
        *[f"| {key} | {instacart[key]['rows']:,} |" for key in ("aisles", "departments", "products", "orders")],
        f"| Prior order products | {lines['prior']['rows']:,} |",
        f"| Train order products | {lines['train']['rows']:,} |", "",
        f"Distinct users: **{orders['users']:,}**. Order evaluation sets: `{json.dumps(orders['eval_set_counts'])}`.", "",
        "### Integrity checks", "", "| Check | Count |", "| --- | ---: |",
    ])
    for key in ("aisles", "departments", "products", "orders"):
        report.append(f"| {key}: duplicate primary IDs | {instacart[key].get('duplicate_ids', 0):,} |")
    for key in ("unknown_aisle_ids", "unknown_department_ids", "blank_names"):
        report.append(f"| products: {key} | {instacart['products'].get(key, 0):,} |")
    for split in ("prior", "train"):
        for key in ("unknown_product_ids", "unknown_order_ids", "wrong_eval_set",
                    "fragmented_order_groups", "duplicate_products_within_contiguous_order_group",
                    "groups_with_noncontiguous_cart_positions", "orders_missing_product_rows"):
            report.append(f"| {split}: {key} | {lines[split].get(key, 0):,} |")
    report.extend([
        "", "The JSON summary contains additional numeric, flag, and missing-value checks. A global order/product duplicate conclusion requires zero fragmented order groups.",
        "", "Missing `days_since_prior_order` on first orders is expected; cart position and reorder flags are not quantities.",
        "", "## Food.com recipes", "", "| Check | Count |", "| --- | ---: |",
    ])
    for key in ("rows", "duplicate_ids", "missing_or_invalid_servings", "unsupported_vector_syntax_rows",
                "empty_ingredient_lists", "ingredient_quantity_length_mismatches",
                "rows_with_missing_ingredient_names", "rows_with_missing_quantity_entries",
                "rows_with_nonpositive_or_unparsed_amounts", "structurally_usable_before_unit_review",
                "meal_shortlist_candidates_before_unit_review", "shortlist_count"):
        report.append(f"| {key} | {recipes.get(key, 0):,} |")
    report.extend([
        "", f"Dedicated ingredient-unit column detected: **{recipes['has_dedicated_ingredient_unit_column']}**.",
        "A structurally usable row is not a verified quantity-aware recipe. Positive numeric amounts and matching list lengths do not establish units, recipe correctness, dietary suitability, or product mappings.",
        "", "Recipe issue counts can overlap. Ingredient/amount checks exclude rows with unsupported vector syntax; servings and identifier checks cover all rows.",
        "", "## Coverage and limitations", "",
        "- All six Instacart CSVs and the complete Food.com recipe CSV were scanned. ZIP CRC is checked by the reader for fully consumed members.",
        "- The archive SHA-256 hashes identify the downloaded files; they were not compared to publisher-provided checksums. Dataset release/version and actual download date are not independently established.",
        "- Review data and Parquet files were inventoried but not scanned. No full-archive integrity claim is made.",
        "- Recipe list parsing is deliberately limited and does not execute source strings. Unsupported rows are counted for review.",
        "- No missing units, prices, pack sizes, or dietary attributes were fabricated. No model has been trained.",
        "- Purchase history remains separate from recipe fulfillment; no product identity joins have been accepted.",
        "", "## Reproduce", "", "```powershell", "python scripts/audit_data.py --config configs/data_audit.json", "```", "",
        "Machine-readable manifest and checks are saved under `data/interim/audit/`. Recipe candidate records remain there rather than in public documentation.",
        "", "## Next task", "",
        "Review five meal recipes and establish their actual quantities, units, and servings from recorded sources. Then build their canonical ingredient mappings and a covering 20-option product catalog with explicit pack sizes and simulated prices. Recipes with unresolved units remain excluded from optimization.", "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/data_audit.json"))
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[3]
    instacart = root / config["instacart_archive"]
    foodcom = root / config["foodcom_archive"]
    output = root / config["output_directory"]
    report = root / config["report_path"]
    if not instacart.is_file() or not foodcom.is_file():
        parser.error("Both configured source ZIPs must exist. See data/README.md.")
    csv.field_size_limit(16 * 1024 * 1024)
    started = time.perf_counter()
    print("Hashing and inventorying source archives...", flush=True)
    summary = {
        "audit_format_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "archives": [archive_manifest(instacart), archive_manifest(foodcom)],
        "provenance": {"download_date": "not recorded", "publisher_checksums_verified": False,
                       "instacart_source": "https://www.kaggle.com/competitions/basket-analysis/data",
                       "foodcom_source": "https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews",
                       "note": "User supplied the downloads; URLs identify the intended sources, not independently verified download origins."},
    }
    summary["instacart"] = audit_instacart(instacart)
    print("Reading Food.com recipes...", flush=True)
    summary["foodcom"], candidates = audit_foodcom(foodcom, config["recipe_shortlist_size"])
    summary["duration_seconds"] = round(time.perf_counter() - started, 3)
    output.mkdir(parents=True, exist_ok=True)
    # Write artifacts only after all required source scans finish successfully.
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    candidate_path = output / "recipe_candidates.csv"
    fields = ["source_recipe_id", "name", "category", "source_servings", "ingredient_count",
              "ingredient_names_json", "source_amounts_json", "unit_review_status", "review_status", "optimizer_ready"]
    with candidate_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidates)
    write_report(summary, report)
    print(f"Audit complete in {summary['duration_seconds']:.1f}s. Report: {report}", flush=True)


if __name__ == "__main__":
    main()
