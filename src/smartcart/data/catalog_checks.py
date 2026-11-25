"""Coverage, duplicate, missing-field and target checks for the full catalog."""

from __future__ import annotations

from collections import Counter
from decimal import ROUND_CEILING, Decimal

from smartcart.data.contracts import validate_catalog


def _cheapest_line_cost(line: dict, products: list[dict]) -> int | None:
    best = None
    need = Decimal(line["amount"])
    for p in products:
        if p["ingredient_id"] != line["ingredient_id"] or p["pack_unit"] != line["unit"] or not p["available"]:
            continue
        packs = int((need / Decimal(p["pack_amount"])).to_integral_value(rounding=ROUND_CEILING))
        cost = packs * p["price_minor"]
        best = cost if best is None else min(best, cost)
    return best


def run_catalog_checks(catalog: dict, targets: dict, line_rows: list[dict]) -> dict:
    validation = validate_catalog(catalog)
    products, recipes, ingredients = catalog["products"], catalog["recipes"], catalog["ingredients"]
    used = {line["ingredient_id"] for r in recipes for line in r["ingredients"]}
    per_ingredient = Counter(p["ingredient_id"] for p in products)
    names = Counter(p["name"] for p in products)
    recipe_costs = {}
    for recipe in recipes:
        costs = [_cheapest_line_cost(line, products) for line in recipe["ingredients"]]
        recipe_costs[recipe["id"]] = None if None in costs else sum(costs)
    families = Counter(r["meal_family"] for r in recipes)
    required_fields = {"id", "name", "ingredient_id", "pack_amount", "pack_unit", "price_minor", "currency",
                       "available", "dietary", "attribute_source_id", "simulated_fields", "external_ids"}
    missing_fields = [p["id"] for p in products if required_fields - p.keys()]
    dietary_counts = {key: dict(Counter(p["dietary"][key] for p in products))
                      for key in ("vegetarian", "vegan", "gluten_free", "dairy_free", "nut_free")}
    checks = {
        "recipes_target": len(recipes) >= targets["recipes_min"],
        "meal_families_target": len(families) >= targets["meal_families_min"],
        "products_target": targets["products_min"] <= len(products) <= targets["products_max"],
        "every_recipe_line_covered": all(c is not None for c in recipe_costs.values()),
        "no_duplicate_product_names": max(names.values()) == 1,
        "no_missing_product_fields": not missing_fields,
        "every_ingredient_has_product": all(per_ingredient[i["id"]] > 0 for i in ingredients),
    }
    return {
        "valid_schema": validation["valid"],
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "counts": {
            "recipes": len(recipes),
            "meal_families": len(families),
            "ingredients": len(ingredients),
            "ingredients_used_in_recipes": len(used),
            "distractor_ingredients": len({i["id"] for i in ingredients} - used),
            "products": len(products),
            "products_unavailable": sum(not p["available"] for p in products),
            "recipe_lines": validation["covered_recipe_lines"],
            "aliases": sum(len(i["aliases"]) for i in ingredients),
            "sources": len(catalog["sources"]),
            "conversions": len(catalog["conversions"]),
        },
        "meal_family_sizes": dict(sorted(families.items())),
        "products_per_ingredient": {"min": min(per_ingredient.values()), "max": max(per_ingredient.values()),
                                    "mean": round(len(products) / len(per_ingredient), 2)},
        "line_resolutions": dict(Counter(row["resolution"] or "as_published" for row in line_rows)),
        "dietary_value_counts": dietary_counts,
        "cheapest_complete_basket_minor_at_base_servings": recipe_costs,
        "duplicate_product_names": [n for n, c in names.items() if c > 1],
        "products_missing_fields": missing_fields,
        "independent_recipe_reviews_pending": validation["independent_recipe_reviews_pending"],
    }
