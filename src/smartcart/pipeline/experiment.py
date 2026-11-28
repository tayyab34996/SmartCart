"""Phase 11 experiments: one runner and one scorer for every run (E0–E4, A1–A4).

A run is a parser, a retrieval setting and a selector:

- ``independent_cheapest``: E0's selector (per-line cheapest option in the retrieved
  pool, then post-hoc diet and budget filtering), ``pipeline.e0.select_e0_basket``;
- ``constrained``: Phase 9 CP-SAT (``optimization.cpsat.select_basket``) with the run's
  candidates and history/pair weights over ``configs/solver.json``.

Every run uses the same dialogue (E0's simulated user: one answer, at most
``max_turns`` questions) and the same scoring, always against the **gold** request:

- feasible reference: success = labelled ``valid`` and the gold validator passes;
- infeasible reference: success = the run returns no basket and states infeasibility
  (``over_budget``/``incomplete`` for the independent selector, ``infeasible_in_scope``
  for CP-SAT). A ``solver_timeout`` never counts;
- clarification scenarios additionally need a question to have been asked;
- a false rejection is a feasible reference answered with an infeasibility status.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
import statistics
from pathlib import Path

from smartcart.optimization.cpsat import select_basket
from smartcart.pipeline.e0 import select_e0_basket
from smartcart.retrieval.api import retrieve_candidates
from smartcart.validation.feasibility import resolve_requirements
from smartcart.validation.validator import validate_basket

INFEASIBILITY = {"independent_cheapest": {"over_budget", "incomplete"},
                 "constrained": {"infeasible_in_scope"}}
BASKET_STATUSES = {"valid", "over_budget", "incomplete", "invalid_solution"}


# ------------------------------------------------------------------ configs
def run_settings(config: dict, solver: dict) -> dict:
    """Normalise a run config (E0.json keeps its Phase 5 schema)."""
    if config["run"] == "E0" and "product_text" not in config["retrieval"]:
        retrieval = {**config["retrieval"], "product_text": "legacy"}  # pipeline/e0.py pins it
        parser = {"type": config["parser"]["type"]}
    else:
        retrieval, parser = config["retrieval"], config["parser"]
    selection = config["selection"]
    keys = ("method", "product_text", "top_k")
    out = {"run": config["run"], "parser": parser["type"], "retrieval": {k: retrieval[k] for k in keys},
           "selection": selection, "max_turns": config["max_clarification_turns"]}
    if selection == "constrained":
        cfg = copy.deepcopy(solver)
        cfg["candidates"].update(out["retrieval"])
        cfg["objective"]["fixed_weights"].update(config["weights"])
        out["solver"] = cfg
        out["weights"] = {**cfg["objective"]["fixed_weights"], **cfg["objective"]["weights"]}
    return out


# ------------------------------------------------------------------ lock
def verify_lock(root: Path, lock_path: Path) -> dict[str, bool]:
    """SHA-256 of each locked file's UTF-8 text (line endings normalised) against the lock."""
    rows = re.findall(r"\| `([^`]+)` \| `([0-9a-f]{64})` \| locked \|", lock_path.read_text(encoding="utf-8"))
    if not rows:
        raise ValueError("no locked files found in the lock document")
    out = {}
    for path, digest in rows:
        text = (root / path).read_text(encoding="utf-8")
        out[path] = hashlib.sha256(text.encode("utf-8")).hexdigest() == digest
    return out


# ------------------------------------------------------------------ running
def candidates(request: dict, catalog: dict, retrieval: dict) -> dict[str, list[str]]:
    """The retrieved pool per requirement line (as both selectors see it)."""
    try:
        lines = resolve_requirements(request, catalog)["lines"]
    except Exception:  # noqa: BLE001 - an unresolvable request has no pool
        return {}
    return {line["ingredient_id"]: [c["product_id"] for c in retrieve_candidates(
        line["ingredient_id"], catalog, method=retrieval["method"], top_k=retrieval["top_k"],
        product_text=retrieval["product_text"])] for line in lines}


def select(request: dict, catalog: dict, settings: dict, pair_fn=None, history_fn=None) -> dict:
    if request["intent"] == "unsupported":
        return {"status": "unsupported", "purchased": [], "total_cost_minor": 0}
    if request["needs_clarification"]:
        return {"status": "needs_clarification", "purchased": [], "total_cost_minor": 0}
    r = settings["retrieval"]
    if settings["selection"] == "independent_cheapest":
        return select_e0_basket(request, catalog, method=r["method"], top_k=r["top_k"], product_text=r["product_text"])
    return select_basket(request, catalog, settings["solver"], pair_fn=pair_fn, history_fn=history_fn)


def run_scenario(scenario: dict, catalog: dict, settings: dict, parser=None, mode: str = "gold_input",
                 pair_fn=None, history_fn=None) -> dict:
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
        while request["needs_clarification"] and turns < settings["max_turns"]:
            asked.append(request["clarification_type"])
            if answer is None:
                break
            request = parser.answer(request, answer)
            turns += 1
            answer = None  # the simulated user answers once
    basket = select(request, catalog, settings, pair_fn, history_fn)
    return {"request": request, "clarifications_asked": asked, "turns": turns, "status": basket["status"],
            "basket": basket}


def score(result: dict, scenario: dict, catalog: dict, selection: str) -> dict:
    clarify = scenario["label"] == "clarification"
    reference = scenario["resolved_request"] if clarify else scenario["gold_request"]
    reference_label = scenario["resolved_checker"]["label"] if clarify else scenario["label"]
    status = result["status"]
    purchased = result["basket"].get("purchased", [])
    validation = validate_basket(reference, purchased, catalog) if status in BASKET_STATUSES else None
    labelled_valid = status == "valid"
    states_infeasible = status in INFEASIBILITY[selection]
    outcome_ok = (labelled_valid and validation["valid"]) if reference_label == "feasible" else states_infeasible
    first_question = result["clarifications_asked"][0] if result["clarifications_asked"] else None
    return {
        "success": (first_question is not None and outcome_ok) if clarify else outcome_ok,
        "reference_label": reference_label,
        "outcome_ok": outcome_ok,
        "labelled_valid": labelled_valid,
        "violation_among_valid": bool(labelled_valid and not validation["valid"]),
        "violations": [v["type"] for v in validation["violations"]] if validation else [],
        "coverage": validation["coverage"] if validation else 0.0,
        "asked_clarification": first_question is not None,
        "unnecessary_clarification": (not clarify) and first_question is not None,
        "clarification_type_match": (first_question == scenario["gold_request"]["clarification_type"])
        if clarify else None,
        "false_rejection": reference_label == "feasible" and states_infeasible,
        "timeout": status == "solver_timeout",
    }


def row(scenario: dict, result: dict, scored: dict, catalog: dict, settings: dict, mode: str,
        seed: int | None) -> dict:
    """One JSONL row per scenario x run (latency is kept in a separate, machine-dependent file)."""
    request, basket = result["request"], result["basket"]
    solver = [{k: s[k] for k in ("model", "solver_status", "optimality_proven", "time_limit_s")}
              for s in basket.get("solver", [])]
    return {"scenario_id": scenario["scenario_id"], "family_id": scenario["family_id"], "label": scenario["label"],
            "design": scenario["design"], "run": settings["run"], "mode": mode, "seed": seed,
            "extracted": {k: request.get(k) for k in ("intent", "recipe_id", "servings", "items", "pantry",
                                                      "budget_minor", "diet", "exclusions", "user_id",
                                                      "needs_clarification", "clarification_type")},
            "clarifications_asked": result["clarifications_asked"], "turns": result["turns"],
            "candidates": candidates(request, catalog, settings["retrieval"])
            if not request.get("needs_clarification") and request.get("intent") != "unsupported" else {},
            "status": result["status"], "reason": basket.get("reason"),
            "selected": [{k: p.get(k) for k in ("ingredient_id", "product_id", "pack_count", "line_cost_minor")}
                         for p in basket.get("purchased", [])],
            "total_cost_minor": basket.get("total_cost_minor"),
            "suggested_budget_minor": basket.get("suggested_budget_minor"),
            "solver": solver, "score": scored}


# ------------------------------------------------------------------ metrics
def _rate(num: int, den: int) -> float | None:
    return round(num / den, 6) if den else None


def summarize(rows: list[dict]) -> dict:
    def label(name):
        return [r for r in rows if r["label"] == name]

    feasible, infeasible, clar = label("feasible"), label("infeasible"), label("clarification")
    valid = [r for r in rows if r["score"]["labelled_valid"]]
    statuses = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    history = [r for r in rows if r["extracted"].get("user_id") is not None]
    return {
        "scenarios": len(rows),
        "success": sum(r["score"]["success"] for r in rows),
        "success_rate": _rate(sum(r["score"]["success"] for r in rows), len(rows)),
        "valid_complete_success_feasible": _rate(sum(r["score"]["success"] for r in feasible), len(feasible)),
        "feasible": {"scenarios": len(feasible), "success": sum(r["score"]["success"] for r in feasible)},
        "mean_coverage_feasible": round(statistics.mean(r["score"]["coverage"] for r in feasible), 6)
        if feasible else None,
        "outputs_labelled_valid": len(valid),
        "violations_among_valid": sum(r["score"]["violation_among_valid"] for r in rows),
        "infeasible": {"scenarios": len(infeasible), "detected": sum(r["score"]["success"] for r in infeasible)},
        "infeasible_detection_rate": _rate(sum(r["score"]["success"] for r in infeasible), len(infeasible)),
        "false_rejections": sum(r["score"]["false_rejection"] for r in rows),
        "clarification": {"scenarios": len(clar), "success_within_turns": sum(r["score"]["success"] for r in clar),
                          "asked": sum(r["score"]["asked_clarification"] for r in clar),
                          "type_match": sum(bool(r["score"]["clarification_type_match"]) for r in clar)},
        "clarification_success_rate": _rate(sum(r["score"]["success"] for r in clar), len(clar)),
        "unnecessary_clarifications": sum(r["score"]["unnecessary_clarification"] for r in rows),
        "solver_timeouts": sum(r["score"]["timeout"] for r in rows),
        "statuses": dict(sorted(statuses.items())),
        "has_history_subset": {"scenarios": len(history), "success": sum(r["score"]["success"] for r in history)},
    }


SEED_KEYS = ("success_rate", "valid_complete_success_feasible", "mean_coverage_feasible",
             "infeasible_detection_rate", "clarification_success_rate", "violations_among_valid",
             "false_rejections", "unnecessary_clarifications")


def across_seeds(per_seed: dict[str, dict]) -> dict:
    out = {}
    for key in SEED_KEYS:
        values = [m[key] for m in per_seed.values() if m[key] is not None]
        if values:
            out[key] = {"mean": round(statistics.mean(values), 6), "std": round(statistics.pstdev(values), 6),
                        "min": min(values), "max": max(values)}
    return out


def family_bootstrap(a: dict[str, float], b: dict[str, float], families: dict[str, str], resamples: int,
                     seed: int) -> dict:
    """Paired difference in mean scenario success (a - b), resampling whole families.

    ``a`` and ``b`` map scenario ID to success (a seed mean for multi-seed runs)."""
    ids = sorted(a)
    if sorted(b) != ids:
        raise ValueError("the runs cover different scenarios")
    by_family: dict[str, list[str]] = {}
    for sid in ids:
        by_family.setdefault(families[sid], []).append(sid)
    fams = sorted(by_family)
    rng = random.Random(seed)
    observed = sum(a[s] - b[s] for s in ids) / len(ids)
    diffs = []
    for _ in range(resamples):
        chosen = [rng.choice(fams) for _ in fams]
        members = [s for f in chosen for s in by_family[f]]
        diffs.append(sum(a[s] - b[s] for s in members) / len(members))
    diffs.sort()
    lo, hi = diffs[int(0.025 * resamples)], diffs[int(0.975 * resamples) - 1]
    return {"difference": round(observed, 6), "ci95": [round(lo, 6), round(hi, 6)], "families": len(fams),
            "scenarios": len(ids), "resamples": resamples}


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n"


def jsonl_text(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
