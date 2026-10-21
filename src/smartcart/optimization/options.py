from decimal import Decimal

from smartcart.optimization.costs import line_cost_minor
from smartcart.optimization.packs import packs_needed
from smartcart.recipes.quantities import missing_amount


def evaluate_product_option(ingredient_id: str, required_amount: Decimal,pantry_amount: Decimal,
unit: str, product: dict,) -> dict:
    if ingredient_id !=product['ingredient_id'] or unit !=product['pack_unit'] or not product['available']:
        raise ValueError("Product ingredient, unit, or availability is incompatible.")
    pack_amount=Decimal(product["pack_amount"])
    missing=missing_amount(required_amount, pantry_amount)
    pack_count=packs_needed(missing, pack_amount)
    cost=line_cost_minor(pack_count, product["price_minor"])
    surplus=pack_count*pack_amount-missing
    return {
    "product_id": product["id"],
    "missing_amount": missing,
    "pack_count": pack_count,
    "line_cost_minor": cost,
    "surplus_amount": surplus,
    "unit": unit,
    "currency": product["currency"],
}