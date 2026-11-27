"""Basket scenarios with constrained selection (Phase 9; the E3/E4 selector in Phase 11).

The dialogue is the same as E0's (``pipeline/e0.py``): in ``gold_input`` mode a
clarification scenario's gold question counts as asked and the resolved request is
used; in ``end_to_end`` mode the parser asks, the simulated user answers once, and at
most ``max_turns`` questions are asked. Selection is ``optimization.cpsat.select_basket``.

Scoring follows E0 with one difference: for an infeasible scenario the correct outcome
is ``infeasible_in_scope`` (proven), and a ``solver_timeout`` is never counted as a
correct infeasibility.
"""

from __future__ import annotations

from smartcart.explanations import explain
from smartcart.optimization.cpsat import select_basket
from smartcart.validation.validator import validate_basket

BASKET_STATUSES = {"valid", "invalid_solution"}


def run_scenario(scenario: dict, catalog: dict, config: dict, parser=None, mode: str = "gold_input",
                 pair_fn=None, history_fn=None) -> dict:
    if mode not in {"gold_input", "end_to_end"}:
        raise ValueError(mode)
    max_turns = config["max_clarification_turns"]
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
    basket = select_basket(request, catalog, config, pair_fn=pair_fn, history_fn=history_fn)
    return {"scenario_id": scenario["scenario_id"], "family_id": scenario["family_id"], "label": scenario["label"],
            "design": scenario["design"], "mode": mode, "request": request, "clarifications_asked": asked,
            "turns": turns, "status": basket["status"], "basket": basket,
            "explanation": explain(basket, request, catalog)}


def score_scenario(result: dict, scenario: dict, catalog: dict) -> dict:
    """Score against the gold request (the resolved request for clarification scenarios)."""
    clarify = scenario["label"] == "clarification"
    reference = scenario["resolved_request"] if clarify else scenario["gold_request"]
    reference_label = scenario["resolved_checker"]["label"] if clarify else scenario["label"]
    status = result["status"]
    purchased = result["basket"]["purchased"]
    validation = validate_basket(reference, purchased, catalog) if status in BASKET_STATUSES else None
    labelled_valid = status == "valid"
    if reference_label == "feasible":
        outcome_ok = labelled_valid and validation["valid"]
    else:
        outcome_ok = status == "infeasible_in_scope"
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
        "false_rejection": reference_label == "feasible" and status == "infeasible_in_scope",
        "timeout": status == "solver_timeout",
    }
