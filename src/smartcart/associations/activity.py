"""Does the association term change product selection? (Phase 8, task 6)

The selector chooses one eligible product per requirement line; the lines themselves
are fixed by the request. A pair or history term can change the choice only if its value
differs between the options of a line (history) or between option pairs of two lines
(pair score). With ingredient-level rules every product of an ingredient scores the same,
so both spreads are expected to be zero. This module measures it on real requests.
"""

from __future__ import annotations

from itertools import combinations

from smartcart.validation.feasibility import line_options, resolve_requirements


def scenario_request(scenario: dict) -> dict | None:
    request = scenario.get("gold_request") or {}
    if request.get("needs_clarification"):
        request = scenario.get("resolved_request") or {}
    if request.get("intent") == "unsupported" or not (request.get("recipe_id") or request.get("items")):
        return None
    return request


def term_spread(request: dict, catalog: dict, pair_fn, history_fn) -> dict:
    resolved = resolve_requirements(request, catalog)
    diet = list(request.get("diet") or [])
    exclusions = set(request.get("exclusions") or [])
    lines = [line_options(line, catalog["products"], diet, exclusions)[0] for line in resolved["lines"]]
    lines = [opts for opts in lines if opts]
    pair_spread, pair_values = 0.0, set()
    for a_opts, b_opts in combinations(lines, 2):
        values = {round(pair_fn(a["product_id"], b["product_id"]), 9) for a in a_opts for b in b_opts}
        pair_values |= values
        pair_spread = max(pair_spread, max(values) - min(values))
    user = request.get("user_id")
    history_spread, history_nonzero = 0.0, False
    if user is not None:
        for opts in lines:
            values = {round(history_fn(user, o["product_id"]), 9) for o in opts}
            history_nonzero |= any(v > 0 for v in values)
            history_spread = max(history_spread, max(values) - min(values))
    return {"lines_with_options": len(lines), "options": [len(o) for o in lines],
            "pair_spread": round(pair_spread, 9), "pair_nonzero": any(v > 0 for v in pair_values),
            "has_user": user is not None, "history_spread": round(history_spread, 9),
            "history_nonzero": history_nonzero}


def measure(scenarios: list[dict], catalog: dict, pair_fn, history_fn) -> dict:
    rows = []
    for s in scenarios:
        request = scenario_request(s)
        if request is None:
            continue
        rows.append({"scenario_id": s["scenario_id"], **term_spread(request, catalog, pair_fn, history_fn)})
    multi = [r for r in rows if r["lines_with_options"] >= 2]
    users = [r for r in rows if r["has_user"]]
    return {
        "scenarios": len(rows),
        "with_two_or_more_lines": len(multi),
        "lines_with_more_than_one_option": sum(sum(n > 1 for n in r["options"]) for r in rows),
        "pair_term_nonzero": sum(r["pair_nonzero"] for r in multi),
        "pair_term_varies_with_choice": sum(r["pair_spread"] > 0 for r in multi),
        "with_history_user": len(users),
        "history_term_nonzero": sum(r["history_nonzero"] for r in users),
        "history_term_varies_with_choice": sum(r["history_spread"] > 0 for r in users),
        "rows": rows,
    }
