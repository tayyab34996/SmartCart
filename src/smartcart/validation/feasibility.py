"""Gold feasibility checker for structured basket requests (Phase 4, D2).

The supported basket model (BUILD_PHASES section 4.3 and docs/benchmark_policy.md):

- Requirements are the recipe lines scaled to the requested servings (the recipe's base
  servings when none are given) plus any explicit items, aggregated per ingredient and unit.
- Pantry amounts (in the requirement's unit) are subtracted. A line fully covered by the
  pantry needs no purchase.
- An excluded ingredient is dropped from the requirements, and none of its products may
  be bought.
- Each remaining line is bought as **one product type** in the minimum number of whole
  packs. Mixing products for one line and multi-ingredient bundles are out of scope.
- A product is eligible for a line if it has the same ingredient and unit, is available,
  and every requested diet is ``"allowed"``. ``"unknown"`` never satisfies a diet.
- The basket is feasible if every remaining line has an eligible product and the
  minimum total cost is within the budget (no budget means no cost limit).

The minimum cost is found by depth-first enumeration over every combination of eligible
options. Pruning only removes branches whose lower bound already exceeds the best basket
found, so the minimum is exact. ``prune=False`` enumerates every combination.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from smartcart.data.contracts import requirements_for

DIETS = ("vegetarian", "vegan", "gluten_free", "dairy_free", "nut_free")
AMOUNT_STEP = Decimal("0.001")


def quantize_amount(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_STEP, rounding=ROUND_CEILING)


def resolve_requirements(request: dict, catalog: dict) -> dict:
    """Return remaining purchase lines plus what pantry and exclusions removed."""
    totals: dict[tuple[str, str], Decimal] = {}
    if request.get("recipe_id"):
        recipe = next((r for r in catalog["recipes"] if r["id"] == request["recipe_id"]), None)
        if recipe is None:
            raise ValueError(f"unknown recipe {request['recipe_id']}")
        servings = request.get("servings") or recipe["base_servings"]
        for line in requirements_for(catalog, request["recipe_id"], servings):
            key = (line["ingredient_id"], line["unit"])
            totals[key] = totals.get(key, Decimal(0)) + Decimal(line["amount"])
    for item in request.get("items") or []:
        if item.get("amount") is None:
            raise ValueError(f"item {item['ingredient_id']} has no amount")
        key = (item["ingredient_id"], item["unit"])
        totals[key] = totals.get(key, Decimal(0)) + Decimal(item["amount"])

    pantry = request.get("pantry") or {}
    excluded = set(request.get("exclusions") or [])
    units_of: dict[str, list[str]] = {}
    for ingredient, unit in totals:
        units_of.setdefault(ingredient, []).append(unit)
    remaining, covered, dropped = [], [], []
    for (ingredient, unit), amount in totals.items():
        if ingredient in excluded:
            dropped.append({"ingredient_id": ingredient, "unit": unit, "amount": str(quantize_amount(amount))})
            continue
        have = Decimal(0)
        if ingredient in pantry:
            if pantry[ingredient] is None:
                raise ValueError(f"pantry amount for {ingredient} is unknown")
            if len(units_of[ingredient]) > 1:
                raise ValueError(f"pantry amount for {ingredient} is ambiguous across units")
            have = Decimal(pantry[ingredient])
        need = quantize_amount(max(Decimal(0), amount - have))
        line = {"ingredient_id": ingredient, "unit": unit, "required": str(quantize_amount(amount)),
                "pantry": str(quantize_amount(have)), "need": str(need)}
        (covered if need == 0 else remaining).append(line)
    return {
        "lines": remaining,
        "covered_by_pantry": covered,
        "excluded_lines": dropped,
        "ignored_pantry_keys": sorted(set(pantry) - set(units_of)),
    }


def line_options(line: dict, products: list[dict], diet: list[str], exclusions: set[str]) -> tuple[list[dict], dict]:
    """Eligible options for one line, cheapest first, plus counts explaining any gap."""
    need = Decimal(line["need"])
    same = [p for p in products if p["ingredient_id"] == line["ingredient_id"] and p["pack_unit"] == line["unit"]]
    available = [p for p in same if p["available"]]
    diet_ok = [p for p in available if all(p["dietary"].get(d) == "allowed" for d in diet)]
    eligible = [] if line["ingredient_id"] in exclusions else diet_ok
    options = []
    for product in eligible:
        pack = Decimal(product["pack_amount"])
        packs = int((need / pack).to_integral_value(rounding=ROUND_CEILING))
        options.append({"ingredient_id": line["ingredient_id"], "product_id": product["id"], "pack_count": packs,
                        "line_cost_minor": packs * product["price_minor"],
                        "surplus": str(quantize_amount(packs * pack - need)), "unit": line["unit"]})
    options.sort(key=lambda o: (o["line_cost_minor"], o["product_id"]))
    counts = {"same_ingredient_and_unit": len(same), "available": len(available), "diet_allowed": len(diet_ok),
              "eligible": len(options)}
    return options, counts


def _search(option_lists: list[list[dict]], prune: bool) -> tuple[int | None, list[dict], int]:
    """Exact minimum-cost combination (one option per line) by depth-first search."""
    floors = [min(o["line_cost_minor"] for o in opts) for opts in option_lists]
    suffix = [0] * (len(option_lists) + 1)
    for i in range(len(option_lists) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + floors[i]
    best_cost, best, visited = None, [], 0
    chosen: list[dict] = []

    def visit(i: int, cost: int) -> None:
        nonlocal best_cost, best, visited
        if prune and best_cost is not None and cost + suffix[i] >= best_cost:
            return
        if i == len(option_lists):
            visited += 1
            if best_cost is None or cost < best_cost:
                best_cost, best = cost, list(chosen)
            return
        for option in option_lists[i]:
            chosen.append(option)
            visit(i + 1, cost + option["line_cost_minor"])
            chosen.pop()

    visit(0, 0)
    return best_cost, best, visited


def check_feasibility(request: dict, catalog: dict, prune: bool = True) -> dict:
    """Label a gold request and return its minimum feasible cost and cheapest basket."""
    if request.get("intent") == "unsupported":
        return {"label": "unsupported", "reason": "unsupported_intent"}
    if request.get("needs_clarification"):
        return {"label": "clarification", "reason": request.get("clarification_type")}
    diet = list(request.get("diet") or [])
    unknown = set(diet) - set(DIETS)
    if unknown:
        raise ValueError(f"unsupported diet values {sorted(unknown)}")
    resolved = resolve_requirements(request, catalog)
    exclusions = set(request.get("exclusions") or [])
    option_lists, gaps = [], []
    for line in resolved["lines"]:
        options, counts = line_options(line, catalog["products"], diet, exclusions)
        option_lists.append(options)
        if not options:
            gaps.append({"ingredient_id": line["ingredient_id"], "unit": line["unit"], **counts})
    base = {"resolved": resolved, "options_per_line": [len(o) for o in option_lists]}
    if gaps:
        return {"label": "infeasible", "reason": "no_eligible_option", "ingredients_without_option": gaps,
                "min_cost_minor": None, "basket": [], **base}
    if not option_lists:
        cost, basket, visited = 0, [], 1
    else:
        cost, basket, visited = _search(option_lists, prune)
    budget = request.get("budget_minor")
    within = budget is None or cost <= budget
    return {"label": "feasible" if within else "infeasible",
            "reason": "within_budget" if within else "budget_below_minimum_cost",
            "min_cost_minor": cost, "budget_minor": budget, "basket": basket,
            "complete_combinations_visited": visited, **base}
