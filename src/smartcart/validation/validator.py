"""Independent basket validator (used from Phase 5; the D7 solver in Phase 9 reuses it).

Given a request and the purchased lines (product ID and pack count only), the validator
recomputes everything from catalog records:

- the required lines under the benchmark policy (``resolve_requirements``);
- for each purchased line: the product exists and is available, its ingredient is
  required and not excluded, its unit matches, every requested diet is ``"allowed"``,
  the packs cover the need, and the line cost is ``packs x price``;
- every required line is bought exactly once;
- the recomputed total is within the budget (an inclusive cap).

A basket is valid only if there are no violations. Coverage is the share of required
lines bought with a product that passes every line check.
"""

from __future__ import annotations

from decimal import Decimal

from smartcart.validation.feasibility import resolve_requirements


def validate_basket(request: dict, lines: list[dict], catalog: dict) -> dict:
    products = {p["id"]: p for p in catalog["products"]}
    resolved = resolve_requirements(request, catalog)
    need = {(line["ingredient_id"], line["unit"]): Decimal(line["need"]) for line in resolved["lines"]}
    required_ingredients = {iid for iid, _ in need}
    excluded = set(request.get("exclusions") or [])
    diet = list(request.get("diet") or [])
    violations: list[dict] = []
    bought: dict[tuple[str, str], int] = {}
    good: set[tuple[str, str]] = set()
    total = 0

    def flag(kind: str, **detail) -> None:
        violations.append({"type": kind, **detail})

    for line in lines:
        pid = line.get("product_id")
        product = products.get(pid)
        if product is None:
            flag("unknown_product", product_id=pid)
            continue
        packs = line.get("pack_count")
        if type(packs) is not int or packs < 1:
            flag("invalid_pack_count", product_id=pid, pack_count=packs)
            continue
        cost = packs * product["price_minor"]
        total += cost
        if "line_cost_minor" in line and line["line_cost_minor"] != cost:
            flag("line_cost_mismatch", product_id=pid, stated=line["line_cost_minor"], recomputed=cost)
        iid, unit = product["ingredient_id"], product["pack_unit"]
        key = (iid, unit)
        bought[key] = bought.get(key, 0) + 1
        ok = True
        if iid in excluded:
            flag("excluded_ingredient", product_id=pid, ingredient_id=iid)
            ok = False
        elif key not in need:
            kind = "wrong_unit" if iid in required_ingredients else "unrequested_ingredient"
            flag(kind, product_id=pid, ingredient_id=iid, unit=unit)
            ok = False
        if not product["available"]:
            flag("unavailable_product", product_id=pid)
            ok = False
        bad_diets = [d for d in diet if product["dietary"].get(d) != "allowed"]
        if bad_diets:
            flag("diet_violation", product_id=pid, diets=bad_diets,
                 labels={d: product["dietary"].get(d) for d in bad_diets})
            ok = False
        if key in need and packs * Decimal(product["pack_amount"]) < need[key]:
            flag("insufficient_quantity", product_id=pid, need=str(need[key]),
                 bought=str(packs * Decimal(product["pack_amount"])))
            ok = False
        if ok and key in need:
            good.add(key)
    for key, count in bought.items():
        if count > 1:
            flag("duplicate_line", ingredient_id=key[0], unit=key[1], count=count)
            good.discard(key)
    for key in need:
        if key not in bought:
            flag("missing_ingredient", ingredient_id=key[0], unit=key[1])
    budget = request.get("budget_minor")
    if budget is not None and total > budget:
        flag("over_budget", total_cost_minor=total, budget_minor=budget)
    coverage = 1.0 if not need else len(good) / len(need)
    return {"valid": not violations, "violations": violations, "total_cost_minor": total,
            "coverage": round(coverage, 6), "required_lines": len(need), "covered_lines": len(good)}
