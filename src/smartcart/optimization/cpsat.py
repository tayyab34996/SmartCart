"""Constrained basket selection with CP-SAT (Phase 9, D7).

The plan's six steps:

1. **Resolve** the recipe or list, scale to servings, aggregate repeated ingredients and
   subtract the pantry (``resolve_requirements``, the gold policy).
2. **Eligible options per line**: candidates come from frozen MiniLM retrieval (the top
   ``k`` for the ingredient's canonical name). Hard rules decide which candidates are
   options at all: same ingredient and unit, available, every requested diet
   ``"allowed"``, ingredient not excluded. One product maps to one ingredient; bundles do
   not exist in the catalog. Hard rules never enter the objective.
3. **Option cost**: the minimum whole packs covering the need, and packs x price.
4. **CP-SAT**: one Boolean per option, exactly one option per line, and the sum of the
   chosen integer costs <= ``budget_minor``. The integer objective maximises relevance +
   history + pair bonuses (pairs as AND-linked Booleans) minus cost and surplus
   penalties, each term normalised to [0, 1] and scaled by ``scale``. Every main
   coefficient is multiplied by ``TIE_MULTIPLIER`` and a tie-break (cheaper option, then
   product ID) is added below it, so the optimum is unique and reproducible.
5. **Statuses**: ``valid``, ``no_basket_in_candidate_pool`` (when expansion is off),
   ``infeasible_in_scope`` (proven: no eligible product, or the full-catalog model is
   infeasible under the budget), ``solver_timeout`` (never infeasible), plus
   ``needs_clarification``, ``unsupported`` and ``invalid_request`` from the request.
6. **Validation**: the independent Phase 5 validator recomputes the basket from catalog
   IDs and pack counts; a basket is labelled ``valid`` only if it passes.
"""

from __future__ import annotations

import time
from decimal import ROUND_CEILING, Decimal
from itertools import combinations

from ortools.sat.python import cp_model

from smartcart.data.contracts import ContractError
from smartcart.retrieval.api import catalog_fingerprint, retrieve_candidates
from smartcart.validation.feasibility import quantize_amount, resolve_requirements
from smartcart.validation.validator import validate_basket

TIE_MULTIPLIER = 10_000
TERMS = ("relevance", "history", "pair", "cost", "surplus")
_RANKINGS: dict[tuple, list[dict]] = {}


def make_option(product: dict, line: dict, relevance: float) -> dict:
    need = Decimal(line["need"])
    pack = Decimal(product["pack_amount"])
    packs = int((need / pack).to_integral_value(rounding=ROUND_CEILING))
    bought = packs * pack
    return {"ingredient_id": line["ingredient_id"], "unit": line["unit"], "need": line["need"],
            "product_id": product["id"], "pack_count": packs, "pack_amount": product["pack_amount"],
            "price_minor": product["price_minor"], "line_cost_minor": packs * product["price_minor"],
            "bought": str(quantize_amount(bought)), "surplus": str(quantize_amount(bought - need)),
            "surplus_share": float((bought - need) / bought) if bought else 0.0,
            "relevance": relevance}


def eligible(product: dict, line: dict, diet: list[str], exclusions: set[str]) -> bool:
    return (product["ingredient_id"] == line["ingredient_id"] and product["pack_unit"] == line["unit"]
            and product["available"] and line["ingredient_id"] not in exclusions
            and all(product["dietary"].get(d) == "allowed" for d in diet))


def line_candidates(line: dict, catalog: dict, cand: dict) -> tuple[list[str], dict[str, float]]:
    """The retrieval pool (top k IDs) and every product's retrieval score for the line.
    The whole-catalog ranking is cached per (catalog, ingredient, method, product text)."""
    key = (catalog_fingerprint(catalog), line["ingredient_id"], cand["method"], cand["product_text"])
    if key not in _RANKINGS:
        _RANKINGS[key] = retrieve_candidates(line["ingredient_id"], catalog, method=cand["method"],
                                             top_k=len(catalog["products"]), product_text=cand["product_text"])
    ranked = _RANKINGS[key]
    scores = {r["product_id"]: r["retrieval_score"] for r in ranked}
    return [r["product_id"] for r in ranked[:cand["top_k"]]], scores


def option_lists(lines: list[dict], catalog: dict, request: dict, cand: dict, expand: set[int]) -> tuple:
    """Options per line from the pool (or the whole catalog for lines in ``expand``)."""
    products = {p["id"]: p for p in catalog["products"]}
    diet = list(request.get("diet") or [])
    exclusions = set(request.get("exclusions") or [])
    out, trace = [], []
    for i, line in enumerate(lines):
        pool, scores = line_candidates(line, catalog, cand)
        ids = list(products) if i in expand else pool
        opts = [make_option(products[pid], line, scores[pid]) for pid in ids
                if eligible(products[pid], line, diet, exclusions)]
        opts.sort(key=lambda o: (o["line_cost_minor"], o["product_id"]))
        in_pool = sum(eligible(products[pid], line, diet, exclusions) for pid in pool)
        out.append(opts)
        trace.append({"ingredient_id": line["ingredient_id"], "unit": line["unit"], "pool_size": len(pool),
                      "eligible_in_pool": in_pool, "expanded": i in expand, "options": len(opts)})
    return out, trace


def solve(options: list[list[dict]], budget: int | None, weights: dict, scale: int, user, pair_fn, history_fn,
          solver_cfg: dict, minimize_cost: bool = False) -> dict:
    """Solve one model. ``minimize_cost`` drops the budget and minimises total cost instead."""
    model = cp_model.CpModel()
    x = [[model.NewBoolVar(f"x{i}_{j}") for j in range(len(opts))] for i, opts in enumerate(options)]
    for row in x:
        model.AddExactlyOne(row)
    cost_expr = sum(o["line_cost_minor"] * v for opts, row in zip(options, x) for o, v in zip(opts, row))
    if minimize_cost:
        model.Minimize(cost_expr)
    else:
        if budget is not None:
            model.Add(cost_expr <= budget)
        n_lines = len(options)
        cost_ref = sum(max(o["line_cost_minor"] for o in opts) for opts in options) or 1
        hist = [[history_fn(user, o["product_id"]) if user is not None else 0.0 for o in opts] for opts in options]
        terms = []
        for i, (opts, row) in enumerate(zip(options, x)):
            for j, (o, v) in enumerate(zip(opts, row)):
                main = (weights["relevance"] * o["relevance"] / n_lines + weights["history"] * hist[i][j] / n_lines
                        - weights["surplus"] * o["surplus_share"] / n_lines
                        - weights["cost"] * o["line_cost_minor"] / cost_ref)
                terms.append((round(scale * main) * TIE_MULTIPLIER - j) * v)  # j = rank by (cost, product ID)
        pair_constant, pair_vars = 0.0, 0
        n_pairs = n_lines * (n_lines - 1) // 2
        for a, b in combinations(range(n_lines), 2):
            table = [[pair_fn(oa["product_id"], ob["product_id"]) for ob in options[b]] for oa in options[a]]
            values = {round(s, 9) for r in table for s in r}
            if len(values) == 1:  # every choice scores the same: a constant, no variables
                pair_constant += values.pop() / n_pairs
                continue
            for ia, r in enumerate(table):
                for ib, s in enumerate(r):
                    coef = round(scale * weights["pair"] * s / n_pairs)
                    if coef > 0:
                        y = model.NewBoolVar(f"y{a}_{ia}_{b}_{ib}")
                        model.AddImplication(y, x[a][ia])
                        model.AddImplication(y, x[b][ib])
                        terms.append(coef * TIE_MULTIPLIER * y)
                        pair_vars += 1
        model.Maximize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_cfg["time_limit_s"]
    solver.parameters.num_workers = solver_cfg["num_workers"]
    solver.parameters.random_seed = solver_cfg["random_seed"]
    start = time.perf_counter()
    status = solver.Solve(model)
    wall = time.perf_counter() - start
    name = solver.StatusName(status)
    out = {"solver_status": name, "optimality_proven": status == cp_model.OPTIMAL,
           "time_limit_s": solver_cfg["time_limit_s"], "wall_time_s": round(wall, 4)}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen = [opts[next(j for j, v in enumerate(row) if solver.Value(v))] for opts, row in zip(options, x)]
        out["chosen"] = chosen
        if not minimize_cost:
            out["pair_constant"] = pair_constant
            out["pair_variables"] = pair_vars
    return out


def _components(chosen: list[dict], options: list[list[dict]], user, pair_fn, history_fn) -> dict:
    n = len(chosen)
    if not n:
        return {t: 0.0 for t in TERMS}
    pairs = list(combinations(chosen, 2))
    cost_ref = sum(max(o["line_cost_minor"] for o in opts) for opts in options) or 1
    return {"relevance": round(sum(o["relevance"] for o in chosen) / n, 6),
            "history": round(sum(history_fn(user, o["product_id"]) if user is not None else 0.0
                                 for o in chosen) / n, 6),
            "pair": round(sum(pair_fn(a["product_id"], b["product_id"]) for a, b in pairs) / len(pairs), 6)
            if pairs else 0.0,
            "cost": round(sum(o["line_cost_minor"] for o in chosen) / cost_ref, 6),
            "surplus": round(sum(o["surplus_share"] for o in chosen) / n, 6)}


def _line_record(o: dict) -> dict:
    return {k: o[k] for k in ("ingredient_id", "unit", "need", "product_id", "pack_count", "pack_amount",
                              "price_minor", "line_cost_minor", "bought", "surplus", "relevance")}


def select_basket(request: dict, catalog: dict, config: dict, pair_fn=None, history_fn=None) -> dict:
    """Constrained selection for one StructuredRequest. Returns the status, the basket,
    the solver log and the trace; ``timing`` holds wall-clock values (machine-dependent)."""
    if pair_fn is None or history_fn is None:
        from smartcart.associations import api

        pair_fn = pair_fn or api.pair_score
        history_fn = history_fn or api.history_score
    budget = request.get("budget_minor")
    base = {"status": None, "reason": None, "lines": [], "purchased": [], "total_cost_minor": 0,
            "budget_minor": budget, "budget_remaining_minor": None, "suggested_budget_minor": None,
            "covered_by_pantry": [], "excluded_lines": [], "solver": [], "trace": {}, "objective": None,
            "validator": None, "timing": {}}
    if request.get("intent") == "unsupported":
        return {**base, "status": "unsupported", "reason": "unsupported_intent"}
    if request.get("needs_clarification"):
        return {**base, "status": "needs_clarification", "reason": request.get("clarification_type")}
    if not request.get("recipe_id") and not request.get("items"):
        return {**base, "status": "invalid_request", "reason": "nothing_to_buy"}
    try:
        resolved = resolve_requirements(request, catalog)
    except (ValueError, ContractError) as exc:
        return {**base, "status": "invalid_request", "reason": str(exc)}
    base.update(covered_by_pantry=resolved["covered_by_pantry"], excluded_lines=resolved["excluded_lines"])
    lines = resolved["lines"]
    weights = {**config["objective"]["fixed_weights"], **config["objective"]["weights"]}
    scale = config["objective"]["scale"]
    cand, solver_cfg = config["candidates"], config["solver"]
    user = request.get("user_id")
    start = time.perf_counter()

    def finish(result: dict) -> dict:
        result["timing"]["total_s"] = round(time.perf_counter() - start, 4)
        result["timing"]["solver_s"] = round(sum(s.pop("wall_time_s", 0.0) for s in result["solver"]), 4)
        return result

    if not lines:  # the pantry covers everything
        validation = validate_basket(request, [], catalog)
        status = "valid" if validation["valid"] else "invalid_solution"
        return finish({**base, "status": status, "reason": "pantry_covers_all", "validator": validation,
                       "budget_remaining_minor": None if budget is None else budget})

    expand: set[int] = set()
    options, trace = option_lists(lines, catalog, request, cand, expand)
    events = []
    empty = [i for i, opts in enumerate(options) if not opts]
    if empty:
        events.append({"event": "no_basket_in_candidate_pool", "lines": [lines[i]["ingredient_id"] for i in empty]})
        if not cand["expand"]:
            return finish({**base, "status": "no_basket_in_candidate_pool", "reason": "line_without_pool_option",
                           "trace": {"lines": trace, "events": events}})
        expand = set(range(len(lines)))
        options, trace = option_lists(lines, catalog, request, cand, expand)
        events.append({"event": "expanded_to_catalog"})
        missing = [lines[i]["ingredient_id"] for i, opts in enumerate(options) if not opts]
        if missing:
            return finish({**base, "status": "infeasible_in_scope", "reason": "no_eligible_option",
                           "trace": {"lines": trace, "events": events, "ingredients_without_option": missing}})
    solves = []
    result = solve(options, budget, weights, scale, user, pair_fn, history_fn, solver_cfg)
    solves.append({"model": "expanded" if expand else "pool", **result})
    if result["solver_status"] == "INFEASIBLE" and not expand:
        events.append({"event": "no_basket_in_candidate_pool", "lines": "budget"})
        if not cand["expand"]:
            return finish({**base, "status": "no_basket_in_candidate_pool", "reason": "pool_infeasible_under_budget",
                           "solver": [_solver_log(s) for s in solves], "trace": {"lines": trace, "events": events}})
        expand = set(range(len(lines)))
        options, trace = option_lists(lines, catalog, request, cand, expand)
        events.append({"event": "expanded_to_catalog"})
        result = solve(options, budget, weights, scale, user, pair_fn, history_fn, solver_cfg)
        solves.append({"model": "expanded", **result})
    status_name = result["solver_status"]
    out = {**base, "trace": {"lines": trace, "events": events}}
    if status_name == "INFEASIBLE":  # proven over every eligible catalog product
        minimum = solve(options, None, weights, scale, user, pair_fn, history_fn, solver_cfg, minimize_cost=True)
        solves.append({"model": "minimum_cost_without_budget", **minimum})
        suggested = sum(o["line_cost_minor"] for o in minimum["chosen"]) if "chosen" in minimum else None
        out.update(status="infeasible_in_scope", reason="budget_below_minimum_cost",
                   suggested_budget_minor=suggested, solver=[_solver_log(s) for s in solves])
        return finish(out)
    if "chosen" not in result:  # UNKNOWN: the time limit was hit before any solution
        out.update(status="solver_timeout", reason="time_limit_without_solution",
                   solver=[_solver_log(s) for s in solves])
        return finish(out)
    chosen = result["chosen"]
    purchased = [{"ingredient_id": o["ingredient_id"], "product_id": o["product_id"], "pack_count": o["pack_count"],
                  "line_cost_minor": o["line_cost_minor"], "unit": o["unit"]} for o in chosen]
    validation = validate_basket(request, purchased, catalog)
    total = sum(o["line_cost_minor"] for o in chosen)
    cheapest = [min(opts, key=lambda o: (o["line_cost_minor"], o["product_id"])) for opts in options]
    out.update(status="valid" if validation["valid"] else "invalid_solution",
               reason="optimal" if result["optimality_proven"] else "feasible_not_proven_optimal",
               lines=[{**_line_record(o), "options": len(opts), "cheapest_option": o["product_id"] == c["product_id"],
                       "cheapest": None if o["product_id"] == c["product_id"] else
                       {k: c[k] for k in ("product_id", "line_cost_minor", "surplus", "relevance")}}
                      for o, opts, c in zip(chosen, options, cheapest)],
               purchased=purchased, total_cost_minor=total,
               budget_remaining_minor=None if budget is None else budget - total,
               objective={"weights": weights, "components": _components(chosen, options, user, pair_fn, history_fn),
                          "pair_constant": round(result.get("pair_constant", 0.0), 6),
                          "pair_variables": result.get("pair_variables", 0)},
               validator=validation, solver=[_solver_log(s) for s in solves])
    return finish(out)


def _solver_log(s: dict) -> dict:
    return {k: v for k, v in s.items() if k not in ("chosen", "pair_constant", "pair_variables")}


def minimum_cost(request: dict, catalog: dict, config: dict) -> int | None:
    """Minimum complete-basket cost over every eligible catalog product (no budget), for
    agreement checks against the Phase 4 enumeration."""
    resolved = resolve_requirements(request, catalog)
    lines = resolved["lines"]
    if not lines:
        return 0
    options, _ = option_lists(lines, catalog, request, config["candidates"], set(range(len(lines))))
    if any(not opts for opts in options):
        return None
    result = solve(options, None, {}, 1, None, None, None, config["solver"], minimize_cost=True)
    return sum(o["line_cost_minor"] for o in result["chosen"]) if "chosen" in result else None
