"""E0 baseline basket: TF-IDF retrieval, independent cheapest selection, post-hoc filtering.

For each remaining requirement line (recipe scaled to servings, plus items, minus pantry,
minus excluded ingredients; ``resolve_requirements`` from the gold policy):

1. **Retrieve** the top ``k`` products for the ingredient with TF-IDF over the whole catalog.
2. **Select independently**: among retrieved products with the line's ingredient and unit
   that are available, take the cheapest by line cost (then surplus, then product ID).
   Lines are chosen one at a time; the budget and diet play no part in the choice.
3. **Filter post hoc**: a selected product that is not ``"allowed"`` for every requested
   diet is removed, leaving the line uncovered. ``unknown`` labels are removed too.

Statuses: ``valid`` (complete and within budget), ``over_budget``, ``incomplete`` (a line
has no compatible candidate in the pool or lost its product to the diet filter),
``no_requirements`` (nothing to buy was identified), ``invalid_request`` (the request
cannot be resolved), plus ``needs_clarification`` and ``unsupported`` from the parser.
Incomplete and invalid outcomes are failures in every metric.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from smartcart.data.contracts import ContractError
from smartcart.retrieval.api import retrieve_candidates
from smartcart.validation.feasibility import quantize_amount, resolve_requirements
from smartcart.validation.validator import validate_basket

BASKET_STATUSES = {"valid", "over_budget", "incomplete"}
NO_BASKET_STATUSES = {"over_budget", "incomplete"}


def _option(product: dict, need: Decimal) -> dict:
    pack = Decimal(product["pack_amount"])
    packs = int((need / pack).to_integral_value(rounding=ROUND_CEILING))
    return {"product_id": product["id"], "pack_count": packs, "line_cost_minor": packs * product["price_minor"],
            "surplus": quantize_amount(packs * pack - need)}


def select_e0_basket(request: dict, catalog: dict, method: str = "tfidf", top_k: int = 10) -> dict:
    base = {"status": None, "lines": [], "purchased": [], "total_cost_minor": 0,
            "budget_minor": request.get("budget_minor"), "budget_remaining_minor": None, "covered_by_pantry": [],
            "excluded_lines": [], "uncovered_ingredients": [], "ignored_pantry_keys": []}
    if not request.get("recipe_id") and not request.get("items"):
        return {**base, "status": "no_requirements"}
    try:
        resolved = resolve_requirements(request, catalog)
    except (ValueError, ContractError) as exc:
        return {**base, "status": "invalid_request", "error": str(exc)}
    products = {p["id"]: p for p in catalog["products"]}
    diet = list(request.get("diet") or [])
    lines = []
    for req in resolved["lines"]:
        need = Decimal(req["need"])
        pool = retrieve_candidates(req["ingredient_id"], catalog, method=method, top_k=top_k)
        compatible = [products[c["product_id"]] for c in pool
                      if products[c["product_id"]]["ingredient_id"] == req["ingredient_id"]
                      and products[c["product_id"]]["pack_unit"] == req["unit"]
                      and products[c["product_id"]]["available"]]
        line = {"ingredient_id": req["ingredient_id"], "unit": req["unit"], "need": req["need"],
                "pool": [c["product_id"] for c in pool], "compatible_in_pool": len(compatible)}
        if not compatible:
            lines.append({**line, "line_status": "no_candidate_in_pool", "product_id": None, "pack_count": 0,
                          "line_cost_minor": 0})
            continue
        best = min((_option(p, need) for p in compatible),
                   key=lambda o: (o["line_cost_minor"], o["surplus"], o["product_id"]))
        line.update(best, surplus=str(best["surplus"]), line_status="selected")
        bad = [d for d in diet if products[best["product_id"]]["dietary"].get(d) != "allowed"]
        if bad:  # post-hoc filter: the product is dropped, the line stays uncovered
            line.update(line_status="removed_by_diet_filter", removed_product_id=best["product_id"],
                        failed_diets=bad, product_id=None, pack_count=0, line_cost_minor=0)
        lines.append(line)
    purchased = [{"ingredient_id": x["ingredient_id"], "product_id": x["product_id"], "pack_count": x["pack_count"],
                  "line_cost_minor": x["line_cost_minor"], "unit": x["unit"]}
                 for x in lines if x["line_status"] == "selected"]
    total = sum(x["line_cost_minor"] for x in purchased)
    uncovered = [x["ingredient_id"] for x in lines if x["line_status"] != "selected"]
    budget = request.get("budget_minor")
    if uncovered:
        status = "incomplete"
    elif budget is not None and total > budget:
        status = "over_budget"
    else:
        status = "valid"
    return {**base, "status": status, "lines": lines, "purchased": purchased, "total_cost_minor": total,
            "budget_remaining_minor": None if budget is None else budget - total,
            "covered_by_pantry": resolved["covered_by_pantry"], "excluded_lines": resolved["excluded_lines"],
            "uncovered_ingredients": uncovered, "ignored_pantry_keys": resolved["ignored_pantry_keys"]}


def run_e0_scenario(scenario: dict, catalog: dict, parser, mode: str, method: str = "tfidf", top_k: int = 10,
                    max_turns: int = 3) -> dict:
    """Run one basket scenario in ``gold_input`` (component-isolated) or ``end_to_end`` mode.

    The simulated user has one answer (``clarification_answer``), given only to
    clarification scenarios. A question on any other scenario gets no answer, so the run
    ends as ``needs_clarification``.
    """
    if mode not in {"gold_input", "end_to_end"}:
        raise ValueError(mode)
    answer = scenario.get("clarification_answer")
    turns, asked = 0, []
    if mode == "gold_input":
        request = scenario["gold_request"]
        if request["needs_clarification"]:
            asked.append(request["clarification_type"])
            request, turns = scenario["resolved_request"], 1
    else:
        request = parser.parse(scenario["text"], request_id=scenario["scenario_id"])
        request["user_id"] = scenario["gold_request"].get("user_id")  # metadata, not parsed from text
        while request["needs_clarification"] and turns < max_turns:
            asked.append(request["clarification_type"])
            if answer is None:
                break
            request = parser.answer(request, answer)
            turns += 1
            answer = None  # the simulated user answers once
    if request["intent"] == "unsupported":
        basket = {"status": "unsupported", "purchased": [], "total_cost_minor": 0}
    elif request["needs_clarification"]:
        basket = {"status": "needs_clarification", "purchased": [], "total_cost_minor": 0}
    else:
        basket = select_e0_basket(request, catalog, method=method, top_k=top_k)
    return {"scenario_id": scenario["scenario_id"], "family_id": scenario["family_id"], "label": scenario["label"],
            "design": scenario["design"], "mode": mode, "request": request, "clarifications_asked": asked,
            "turns": turns, "status": basket["status"], "basket": basket}


def score_e0_scenario(result: dict, scenario: dict, catalog: dict) -> dict:
    """Score a run against the gold request (the resolved request for clarification scenarios)."""
    clarify = scenario["label"] == "clarification"
    reference = scenario["resolved_request"] if clarify else scenario["gold_request"]
    reference_label = scenario["resolved_checker"]["label"] if clarify else scenario["label"]
    status = result["status"]
    validation = validate_basket(reference, result["basket"]["purchased"], catalog) if status in BASKET_STATUSES \
        else None
    labelled_valid = status == "valid"
    if reference_label == "feasible":
        outcome_ok = labelled_valid and validation["valid"]
    else:
        outcome_ok = status in NO_BASKET_STATUSES
    first_question = result["clarifications_asked"][0] if result["clarifications_asked"] else None
    success = (first_question is not None and outcome_ok) if clarify else outcome_ok
    return {
        "success": success,
        "reference_label": reference_label,
        "outcome_ok": outcome_ok,
        "labelled_valid": labelled_valid,
        "violation_among_valid": labelled_valid and not validation["valid"],
        "validator": validation,
        "coverage": validation["coverage"] if validation else 0.0,
        "asked_clarification": first_question is not None,
        "clarification_type_match": (first_question == scenario["gold_request"]["clarification_type"]) if clarify
        else None,
    }
