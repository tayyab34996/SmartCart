"""Build the full SmartCart catalog from the pilot catalog and reviewed CSV inputs.

The build is deterministic: the same inputs always produce the same catalog.
Every product attribute is simulated and declared as such; see docs/data_card.md.
"""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from smartcart.data.contracts import normalized_amount

DIET_CODES = {"A": "allowed", "D": "disallowed", "U": "unknown"}
DIET_KEYS = ("vegetarian", "vegan", "gluten_free", "dairy_free", "nut_free")
SIMULATED_FIELDS = ["name", "pack_amount", "pack_unit", "price_minor", "currency", "available", "dietary"]
BRAND_PREFIX = {"basics": "bas", "select": "sel", "organic": "org"}
RECIPE_PAGE_NOTE = (
    "Ingredient quantities and units checked against the page's US-unit ingredient list "
    "(fetched text, {date}). Servings taken from the Food.com dataset RecipeServings field; "
    "the fetched page text did not display a servings value."
)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def parse_unit_map(spec: str) -> dict[str, list[str]]:
    """Parse 'g:250|500;piece:2' into {'g': ['250', '500'], 'piece': ['2']}."""
    result = {}
    for part in spec.split(";"):
        unit, values = part.split(":")
        result[unit.strip()] = [v.strip() for v in values.split("|")]
    return result


def pack_price_minor(base_per_unit: str, size: str, size_index: int, brand_factor: str,
                     discounts: list[str]) -> int:
    discount = Decimal(discounts[min(size_index, len(discounts) - 1)])
    pkr = Decimal(base_per_unit) * Decimal(size) * discount * Decimal(brand_factor)
    whole = max(pkr.quantize(Decimal("1"), rounding=ROUND_HALF_UP), Decimal("1"))
    return int(whole) * 100


def unit_label(amount: str, unit: str) -> str:
    if unit == "piece":
        return f"{amount} piece" if amount == "1" else f"{amount} pieces"
    return f"{amount} {unit}"


def is_unavailable(product_id: str, every_nth: int) -> bool:
    digest = int(hashlib.sha256(product_id.encode("utf-8")).hexdigest(), 16)
    return digest % every_nth == 0


def build_ingredients(pilot: dict, rows: list[dict], synonyms: list[dict]) -> list[dict]:
    aliases: dict[str, list[str]] = {}
    for row in synonyms:
        aliases.setdefault(row["ingredient_id"], []).append(row["alias"].strip())
    pilot_ingredients = {i["id"]: i for i in pilot["ingredients"]}
    result = []
    for row in rows:
        iid = row["ingredient_id"]
        units = list(parse_unit_map(row["packs"]))
        base = pilot_ingredients.get(iid)
        name = base["name"] if base else row["name"]
        merged = []
        for alias in (base["aliases"] if base else []) + aliases.get(iid, []):
            if alias.casefold() != name.casefold() and alias.casefold() not in {a.casefold() for a in merged}:
                merged.append(alias)
        supported = list(base["supported_units"]) if base else []
        supported += [u for u in units if u not in supported]
        result.append({"id": iid, "name": name, "aliases": merged, "supported_units": supported,
                       "mapping_status": base["mapping_status"] if base else "agent_reviewed"})
    unknown = set(aliases) - {r["ingredient_id"] for r in rows}
    if unknown:
        raise ValueError(f"Synonyms refer to unknown ingredients: {sorted(unknown)}")
    return result


def build_sources(pilot: dict, config: dict, recipe_rows: list[dict]) -> list[dict]:
    sources = list(pilot["sources"]) + list(config["extra_sources"])
    for row in recipe_rows:
        if row["origin"] == "pilot":
            continue
        sources.append({"id": row["recipe_id"], "title": row["name"], "locator": row["locator"],
                        "kind": "recipe_page", "checked_on": config["checked_on"],
                        "notes": RECIPE_PAGE_NOTE.format(date=config["checked_on"])})
    return sources


def build_recipes(pilot: dict, config: dict, recipe_rows: list[dict], line_rows: list[dict],
                  conversions: dict) -> list[dict]:
    pilot_recipes = {r["id"]: r for r in pilot["recipes"]}
    lines_by_recipe: dict[str, list[dict]] = {}
    for line in line_rows:
        lines_by_recipe.setdefault(line["recipe_id"], []).append(line)
    recipes = []
    for row in recipe_rows:
        rid = row["recipe_id"]
        if row["origin"] == "pilot":
            recipes.append({**pilot_recipes[rid], "meal_family": row["meal_family"]})
            continue
        ingredients = []
        for line in lines_by_recipe.get(rid, []):
            record = {"ingredient_id": line["ingredient_id"], "source_ingredient": line["source_ingredient"],
                      "source_amount": line["source_amount"], "source_unit": line["source_unit"],
                      "conversion_id": line["conversion_id"], "unit": line["unit"]}
            record["amount"] = str(normalized_amount(record, conversions[line["conversion_id"]]))
            ingredients.append(record)
        recipes.append({
            "id": rid, "name": row["name"], "source_recipe_id": row["source_recipe_id"], "source_id": rid,
            "base_servings": int(row["base_servings"]),
            "review": {"status": "source_checked", "reviewer": "claude_source_check",
                       "checked_on": config["checked_on"], "independent_review_status": "pending"},
            "scaling_policy": "linear_source_amount_round_up_0.001",
            "scope_notes": row["scope_notes"], "ingredients": ingredients, "meal_family": row["meal_family"],
        })
    orphan = set(lines_by_recipe) - {r["recipe_id"] for r in recipe_rows}
    if orphan:
        raise ValueError(f"Recipe lines refer to unknown recipes: {sorted(orphan)}")
    return recipes


def _product(pid: str, name: str, row: dict, unit: str, size: str, price_minor: int,
             dietary: dict, available: bool) -> dict:
    return {"id": pid, "name": f"SIMULATED {name} {unit_label(size, unit)}", "ingredient_id": row["ingredient_id"],
            "pack_amount": size, "pack_unit": unit, "price_minor": price_minor, "currency": "PKR",
            "available": available, "dietary": dietary, "attribute_source_id": "simulation_v2",
            "simulated_fields": list(SIMULATED_FIELDS), "external_ids": {}}


def build_products(pilot: dict, config: dict, rows: list[dict]) -> list[dict]:
    products = list(pilot["products"])
    pilot_sizes = {(p["ingredient_id"], p["pack_unit"], Decimal(p["pack_amount"])) for p in pilot["products"]}
    brands, discounts = config["brands"], config["pack_size_discount"]
    every_nth = config["unavailable_every_nth"]
    variants: dict[str, list[dict]] = {}
    for variant in config["dietary_variants"]:
        variants.setdefault(variant["ingredient_id"], []).append(variant)
    for row in rows:
        iid = row["ingredient_id"]
        dietary = {key: DIET_CODES[row[key]] for key in DIET_KEYS}
        packs = parse_unit_map(row["packs"])
        prices = parse_unit_map(row["price_pkr_per_unit"])
        for unit, sizes in packs.items():
            base_price = prices[unit][0]
            for index, size in enumerate(sizes):
                if (iid, unit, Decimal(size)) in pilot_sizes:
                    continue
                price = pack_price_minor(base_price, size, index, brands["basics"]["price_factor"], discounts)
                products.append(_product(f"bas_{iid}_{size}{unit}", f"{brands['basics']['label']} {row['name']}",
                                         row, unit, size, price, dict(dietary), True))
            largest = len(sizes) - 1
            pid = f"sel_{iid}_{sizes[largest]}{unit}"
            price = pack_price_minor(base_price, sizes[largest], largest, brands["select"]["price_factor"], discounts)
            products.append(_product(pid, f"{brands['select']['label']} {row['name']}", row, unit,
                                     sizes[largest], price, dict(dietary), not is_unavailable(pid, every_nth)))
        first_unit = next(iter(packs))
        first_sizes = packs[first_unit]
        first_price = prices[first_unit][0]
        if row["category"] in config["organic_categories"]:
            pid = f"org_{iid}_{first_sizes[0]}{first_unit}"
            price = pack_price_minor(first_price, first_sizes[0], 0, brands["organic"]["price_factor"], discounts)
            products.append(_product(pid, f"{brands['organic']['label']} {row['name']}", row, first_unit,
                                     first_sizes[0], price, dict(dietary), not is_unavailable(pid, every_nth)))
        for number, variant in enumerate(variants.get(iid, []), start=1):
            index = min(1, len(first_sizes) - 1)
            size = first_sizes[index]
            pid = f"var{number}_{iid}_{size}{first_unit}"
            price = pack_price_minor(first_price, size, index, brands["select"]["price_factor"], discounts)
            products.append(_product(pid, f"{brands['select']['label']} {variant['name']}", row, first_unit, size,
                                     price, {**dietary, **variant["overrides"]}, True))
    ids = [p["id"] for p in products]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate product IDs generated")
    return products


def build_catalog(root: Path, config: dict) -> dict:
    pilot = json.loads((root / config["pilot_catalog"]).read_text(encoding="utf-8"))
    inputs = {key: read_csv(root / path) for key, path in config["inputs"].items()}
    conversions = list(pilot["conversions"]) + list(config["extra_conversions"])
    conversion_index = {c["id"]: c for c in conversions}
    return {
        "schema_version": 1,
        "purpose": "offline_simulation",
        "currency": "PKR",
        "minor_units_per_major": 100,
        "sources": build_sources(pilot, config, inputs["recipes"]),
        "ingredients": build_ingredients(pilot, inputs["ingredients"], inputs["synonyms"]),
        "conversions": conversions,
        "products": build_products(pilot, config, inputs["ingredients"]),
        "recipes": build_recipes(pilot, config, inputs["recipes"], inputs["recipe_lines"], conversion_index),
    }
