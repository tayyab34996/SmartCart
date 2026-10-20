"""Version-one contracts for the small, explicitly simulated SmartCart catalog."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
from fractions import Fraction
from pathlib import Path


UNITS = {"g", "ml", "piece"}
DIETS = {"vegetarian", "vegan", "gluten_free", "dairy_free", "nut_free"}
STATES = {"allowed", "disallowed", "unknown"}
SIMULATED_FIELDS = {"name", "pack_amount", "pack_unit", "price_minor", "currency", "available", "dietary"}


class ContractError(ValueError):
    """An input does not satisfy the pilot data contract."""


def fields(record: dict, required: set[str], location: str) -> None:
    if not isinstance(record, dict):
        raise ContractError(f"{location}: expected an object")
    missing, extra = required - record.keys(), record.keys() - required
    if missing or extra:
        raise ContractError(f"{location}: missing fields {sorted(missing)}; extra fields {sorted(extra)}")


def text(value, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{location}: expected nonempty text")
    return value


def amount(value, location: str) -> Decimal:
    if not isinstance(value, str):
        raise ContractError(f"{location}: amounts must be decimal strings")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ContractError(f"{location}: invalid decimal") from error
    if not number.is_finite() or number <= 0:
        raise ContractError(f"{location}: expected a finite positive amount")
    return number


def indexed(rows, location: str) -> dict:
    if not isinstance(rows, list) or not rows:
        raise ContractError(f"{location}: expected a nonempty list")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError(f"{location}: each record must be an object")
        identifier = text(row.get("id"), f"{location}.id")
        if identifier in result:
            raise ContractError(f"{location}: duplicate ID {identifier}")
        result[identifier] = row
    return result


def evidence(ids, sources: dict, location: str) -> None:
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in sources for i in ids):
        raise ContractError(f"{location}: every evidence ID must identify a recorded source")


def normalized_amount(line: dict, conversion: dict, scale: Fraction = Fraction(1)) -> Decimal:
    """Recompute from source amounts and round up once to 0.001 base units.

    Fractional pieces may be ingredient requirements; purchasable piece packs must
    contain whole pieces. Conversion coefficients are documented planning values.
    """
    try:
        original = Fraction(line["source_amount"])
    except (ValueError, ZeroDivisionError, TypeError) as error:
        raise ContractError("Recipe source amount must be a positive numeric fraction") from error
    if original <= 0 or scale <= 0:
        raise ContractError("Recipe source amount and serving scale must be positive")
    factor = amount(conversion["factor"], "conversion.factor")
    with localcontext() as context:
        context.prec = 40
        scaled = original * scale
        value = Decimal(scaled.numerator) / Decimal(scaled.denominator) * factor
        try:
            return value.quantize(Decimal("0.001"), rounding=ROUND_CEILING)
        except InvalidOperation as error:
            raise ContractError("Quantity exceeds the supported planning precision") from error


def validate_pilot(data: dict) -> dict:
    """Fail explicitly on invalid records, broken mappings, or unsupported conversions."""
    fields(data, {"schema_version", "purpose", "currency", "minor_units_per_major", "sources",
                  "ingredients", "conversions", "products", "recipes"}, "pilot")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ContractError("Only schema_version 1 is supported")
    if data["purpose"] != "offline_simulation" or data["currency"] != "PKR" or type(data["minor_units_per_major"]) is not int or data["minor_units_per_major"] != 100:
        raise ContractError("Pilot must declare offline simulation with 100 minor units per PKR")
    sources = indexed(data["sources"], "sources")
    ingredients = indexed(data["ingredients"], "ingredients")
    conversions = indexed(data["conversions"], "conversions")
    products = indexed(data["products"], "products")
    recipes = indexed(data["recipes"], "recipes")
    aliases = {}
    for source_id, source in sources.items():
        fields(source, {"id", "title", "locator", "kind", "checked_on", "notes"}, source_id)
        for key, value in source.items():
            text(value, f"{source_id}.{key}")
        if source["kind"] not in {"recipe_page", "metrology_reference", "ingredient_reference", "design_policy"}:
            raise ContractError(f"{source_id}: unsupported source kind")
    for ingredient_id, ingredient in ingredients.items():
        fields(ingredient, {"id", "name", "aliases", "supported_units", "mapping_status"}, ingredient_id)
        text(ingredient["name"], f"{ingredient_id}.name")
        if ingredient["mapping_status"] != "seed_reviewed":
            raise ContractError(f"{ingredient_id}: ingredient mapping has not been reviewed")
        units = ingredient["supported_units"]
        if not isinstance(units, list) or not units or any(not isinstance(u, str) or u not in UNITS for u in units) or len(units) != len(set(units)):
            raise ContractError(f"{ingredient_id}: unsupported or repeated units")
        if not isinstance(ingredient["aliases"], list):
            raise ContractError(f"{ingredient_id}: aliases must be a list")
        for alias in [ingredient["name"], *ingredient["aliases"]]:
            canonical = " ".join(text(alias, f"{ingredient_id}.alias").casefold().split())
            if canonical in aliases and aliases[canonical] != ingredient_id:
                raise ContractError(f"Ambiguous alias: {alias}")
            aliases[canonical] = ingredient_id
    for conversion_id, conversion in conversions.items():
        fields(conversion, {"id", "from_unit", "to_unit", "factor", "ingredient_id", "kind", "evidence_ids"}, conversion_id)
        text(conversion["from_unit"], f"{conversion_id}.from_unit")
        text(conversion["to_unit"], f"{conversion_id}.to_unit")
        text(conversion["kind"], f"{conversion_id}.kind")
        if conversion["to_unit"] not in UNITS:
            raise ContractError(f"{conversion_id}: unsupported target unit")
        amount(conversion["factor"], conversion_id)
        if conversion["ingredient_id"] is not None:
            text(conversion["ingredient_id"], f"{conversion_id}.ingredient_id")
            if conversion["ingredient_id"] not in ingredients:
                raise ContractError(f"{conversion_id}: unknown ingredient restriction")
        if conversion["kind"] not in {"identity", "unit_conversion", "package_definition", "ingredient_specific_reference_estimate"}:
            raise ContractError(f"{conversion_id}: unsupported conversion kind")
        if conversion["kind"] in {"ingredient_specific_reference_estimate", "package_definition"} and conversion["ingredient_id"] is None:
            raise ContractError(f"{conversion_id}: ingredient-specific conversion must identify its ingredient")
        evidence(conversion["evidence_ids"], sources, conversion_id)
    for product_id, product in products.items():
        fields(product, {"id", "name", "ingredient_id", "pack_amount", "pack_unit", "price_minor", "currency",
                         "available", "dietary", "attribute_source_id", "simulated_fields", "external_ids"}, product_id)
        text(product["name"], f"{product_id}.name")
        text(product["ingredient_id"], f"{product_id}.ingredient_id")
        text(product["pack_unit"], f"{product_id}.pack_unit")
        ingredient = ingredients.get(product["ingredient_id"])
        if ingredient is None or product["pack_unit"] not in ingredient["supported_units"]:
            raise ContractError(f"{product_id}: ingredient/unit mapping is invalid")
        quantity = amount(product["pack_amount"], product_id)
        if product["pack_unit"] == "piece" and quantity != quantity.to_integral_value():
            raise ContractError(f"{product_id}: purchasable piece packs must contain whole pieces")
        if type(product["price_minor"]) is not int or product["price_minor"] < 0:
            raise ContractError(f"{product_id}: price_minor must be a nonnegative integer")
        if product["currency"] != data["currency"] or type(product["available"]) is not bool:
            raise ContractError(f"{product_id}: invalid currency or availability")
        fields(product["dietary"], DIETS, f"{product_id}.dietary")
        if any(not isinstance(v, str) or v not in STATES for v in product["dietary"].values()):
            raise ContractError(f"{product_id}: dietary values must be allowed, disallowed, or unknown")
        evidence([product["attribute_source_id"]], sources, product_id)
        if sources[product["attribute_source_id"]]["kind"] != "design_policy":
            raise ContractError(f"{product_id}: pilot product attributes must have simulation provenance")
        if not isinstance(product["simulated_fields"], list) or any(not isinstance(v, str) for v in product["simulated_fields"]) or set(product["simulated_fields"]) != SIMULATED_FIELDS:
            raise ContractError(f"{product_id}: all simulated attributes must be declared")
        if product["external_ids"] != {}:
            raise ContractError(f"{product_id}: external SKU matches are not verified in this pilot")
    covered_lines = 0
    for recipe_id, recipe in recipes.items():
        fields(recipe, {"id", "name", "source_recipe_id", "source_id", "base_servings", "review",
                        "scaling_policy", "scope_notes", "ingredients"}, recipe_id)
        for key in ("name", "source_recipe_id", "scope_notes"):
            text(recipe[key], f"{recipe_id}.{key}")
        evidence([recipe["source_id"]], sources, recipe_id)
        if sources[recipe["source_id"]]["kind"] != "recipe_page":
            raise ContractError(f"{recipe_id}: recipe quantities need a recipe-page source")
        if type(recipe["base_servings"]) is not int or recipe["base_servings"] <= 0:
            raise ContractError(f"{recipe_id}: base_servings must be a positive integer")
        fields(recipe["review"], {"status", "reviewer", "checked_on", "independent_review_status"}, f"{recipe_id}.review")
        for key, value in recipe["review"].items():
            text(value, f"{recipe_id}.review.{key}")
        if recipe["review"]["status"] != "source_checked" or recipe["review"]["independent_review_status"] not in {"pending", "complete"}:
            raise ContractError(f"{recipe_id}: source review is incomplete")
        text(recipe["review"]["reviewer"], f"{recipe_id}.review.reviewer")
        text(recipe["review"]["checked_on"], f"{recipe_id}.review.checked_on")
        if recipe["scaling_policy"] != "linear_source_amount_round_up_0.001":
            raise ContractError(f"{recipe_id}: unsupported scaling policy")
        if not isinstance(recipe["ingredients"], list) or not recipe["ingredients"]:
            raise ContractError(f"{recipe_id}: missing required ingredients")
        seen = set()
        for line in recipe["ingredients"]:
            fields(line, {"ingredient_id", "source_ingredient", "source_amount", "source_unit", "conversion_id", "amount", "unit"}, recipe_id)
            for key in ("ingredient_id", "source_unit", "conversion_id", "unit"):
                text(line[key], f"{recipe_id}.{key}")
            text(line["source_ingredient"], f"{recipe_id}.source_ingredient")
            text(line["source_amount"], f"{recipe_id}.source_amount")
            ingredient = ingredients.get(line["ingredient_id"])
            if ingredient is None or line["unit"] not in ingredient["supported_units"]:
                raise ContractError(f"{recipe_id}: invalid recipe ingredient/unit mapping")
            if line["ingredient_id"] in seen:
                raise ContractError(f"{recipe_id}: aggregate repeated ingredients before admission")
            seen.add(line["ingredient_id"])
            conversion = conversions.get(line["conversion_id"])
            if conversion is None or conversion["from_unit"] != line["source_unit"] or conversion["to_unit"] != line["unit"]:
                raise ContractError(f"{recipe_id}: invalid source-unit conversion")
            if conversion["ingredient_id"] not in {None, line["ingredient_id"]}:
                raise ContractError(f"{recipe_id}: ingredient-specific conversion used for another ingredient")
            if amount(line["amount"], recipe_id) != normalized_amount(line, conversion):
                raise ContractError(f"{recipe_id}: normalized amount disagrees with source and conversion")
            if not any(p["ingredient_id"] == line["ingredient_id"] and p["pack_unit"] == line["unit"] and p["available"] for p in products.values()):
                raise ContractError(f"{recipe_id}: no available product covers {line['ingredient_id']} in {line['unit']}")
            covered_lines += 1
    return {"valid": True, "ingredients": len(ingredients), "products": len(products), "recipes": len(recipes),
            "covered_recipe_lines": covered_lines, "currency": data["currency"],
            "all_products_simulated": True,
            "independent_recipe_reviews_pending": sum(r["review"]["independent_review_status"] == "pending" for r in recipes.values()),
            "warnings": ["All product attributes are simulated; no external SKU matches are established.",
                         "Dietary unknown is not permission for a hard dietary request.",
                         "Flour cup-to-mass conversion is a documented reference estimate, not a measured density."]}


def load_pilot(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_pilot(data)
    return data


def requirements_for(data: dict, recipe_id: str, servings: int) -> list[dict]:
    """Calculate planned ingredient requirements, not product packs or a basket."""
    if type(servings) is not int or servings <= 0:
        raise ContractError("Servings must be a positive integer")
    recipes = {r["id"]: r for r in data["recipes"]}
    if recipe_id not in recipes:
        raise ContractError(f"Unknown recipe: {recipe_id}")
    recipe = recipes[recipe_id]
    conversions = {c["id"]: c for c in data["conversions"]}
    return [{"ingredient_id": line["ingredient_id"],
             "amount": str(normalized_amount(line, conversions[line["conversion_id"]], Fraction(servings, recipe["base_servings"]))),
             "unit": line["unit"]} for line in recipe["ingredients"]]
