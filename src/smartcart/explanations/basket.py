"""Explanations generated from verified records only (Phase 9).

Every sentence is filled from the catalog, the resolved requirements, the validator's
result and the solver's log. Nothing is inferred or invented:

- a basket is explained line by line only when the validator passed;
- a "cheapest" claim is checked against the line's eligible options;
- an infeasible result names the proven reason (no eligible product, or the minimum
  complete-basket cost from the solver) and never relaxes the request;
- a solver timeout is never described as infeasibility.

Prices are simulated PKR, and every summary says so.
"""

from __future__ import annotations

PRICE_NOTE = "Prices are SIMULATED (PKR), not real shop prices."


def diet_names(diet: list[str]) -> str:
    return ", ".join(d.replace("_", "-") for d in diet)


def pkr(minor: int | None) -> str:
    return "n/a" if minor is None else f"PKR {minor / 100:,.2f}"


def _amount(value: str, unit: str) -> str:
    text = value.rstrip("0").rstrip(".") if "." in value else value
    return f"{text} {'pieces' if unit == 'piece' and text != '1' else unit}"


def _names(catalog: dict) -> tuple[dict, dict]:
    products = {p["id"]: p["name"].replace("SIMULATED ", "", 1) for p in catalog["products"]}
    ingredients = {i["id"]: i["name"] for i in catalog["ingredients"]}
    return products, ingredients


def explain_line(line: dict, products: dict, ingredients: dict, diet: list[str]) -> str:
    unit = line["unit"]
    text = (f"{ingredients.get(line['ingredient_id'], line['ingredient_id'])}: {line['pack_count']} x "
            f"{products[line['product_id']]} = {_amount(line['bought'], unit)} for a need of "
            f"{_amount(line['need'], unit)} ({_amount(line['surplus'], unit)} left over), "
            f"{pkr(line['line_cost_minor'])}.")
    if line["cheapest_option"]:
        text += f" Cheapest of the {line['options']} eligible option{'s' if line['options'] != 1 else ''}."
    else:
        c = line["cheapest"]
        reasons = []
        if float(line["surplus"]) < float(c["surplus"]):
            reasons.append("leaves less left over")
        if line["relevance"] > c["relevance"]:
            reasons.append("matches the ingredient more closely")
        why = " and ".join(reasons) if reasons else "scores higher on the objective"
        text += (f" Chosen over the cheaper {products[c['product_id']]} ({pkr(c['line_cost_minor'])}) because it "
                 f"{why}.")
    if diet:
        text += f" Labelled \"allowed\" for {diet_names(diet)} in the catalog."
    return text


def explain(result: dict, request: dict, catalog: dict) -> dict:
    products, ingredients = _names(catalog)
    diet = list(request.get("diet") or [])
    status = result["status"]
    lines, notes = [], [PRICE_NOTE]
    for pantry in result.get("covered_by_pantry", []):
        notes.append(f"Not bought: your pantry covers {ingredients.get(pantry['ingredient_id'])}.")
    for dropped in result.get("excluded_lines", []):
        notes.append(f"Left out: {ingredients.get(dropped['ingredient_id'])} (you excluded it).")
    if status == "valid" and result["validator"] and result["validator"]["valid"]:
        lines = [explain_line(line, products, ingredients, diet) for line in result["lines"]]
        budget = result["budget_minor"]
        total = result["total_cost_minor"]
        summary = f"Basket of {len(lines)} product{'s' if len(lines) != 1 else ''}, total {pkr(total)}"
        summary += "." if budget is None else f" of a {pkr(budget)} budget ({pkr(budget - total)} left)."
        if result["reason"] == "pantry_covers_all":
            summary = "Nothing to buy: your pantry covers every ingredient."
        elif result["reason"] != "optimal":
            notes.append("This is the best basket found within the time limit; it is not proven optimal.")
        notes.append("Every line was re-checked by the independent validator (quantity, unit, diet, "
                     "availability, exclusions, cost and budget).")
    elif status == "infeasible_in_scope" and result["reason"] == "budget_below_minimum_cost":
        summary = (f"No complete basket fits the {pkr(result['budget_minor'])} budget. The cheapest complete basket "
                   f"under the same rules costs {pkr(result['suggested_budget_minor'])}; a budget of at least that "
                   f"would work. Nothing was changed in your request.")
    elif status == "infeasible_in_scope":
        missing = result["trace"].get("ingredients_without_option", [])
        names = ", ".join(ingredients.get(i, i) for i in missing)
        summary = f"No product in the catalog meets every rule for: {names}."
        if diet:
            summary += (f" A product must be labelled \"allowed\" for {diet_names(diet)}; products labelled "
                        f"\"unknown\" never count.")
    elif status == "solver_timeout":
        summary = ("The solver reached its time limit without finding a basket. This is not proof that no basket "
                   "exists.")
    elif status == "needs_clarification":
        summary = f"A question is needed first ({result['reason']})."
    elif status == "unsupported":
        summary = "This request is outside what SmartCart supports."
    elif status == "no_basket_in_candidate_pool":
        summary = "No basket was found among the retrieved candidates, and expanding the search was switched off."
    else:
        summary = f"No basket ({status}: {result.get('reason')})."
    return {"status": status, "summary": summary, "lines": lines, "notes": notes}
