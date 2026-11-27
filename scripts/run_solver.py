"""Constrained selection on the dev basket scenarios, gold input (Phase 9).

Usage:
    python scripts/run_solver.py --select   # apply the weight-selection rule on dev, freeze it in the config
    python scripts/run_solver.py            # run with the frozen weights and write the outputs
    python scripts/run_solver.py --check    # rebuild the committed outputs in memory and compare

Reads ``data/benchmarks/basket_dev.json`` only (the test scenarios are run once in
Phase 11). Every scenario is run component-isolated (gold StructuredRequest; for a
clarification scenario the gold question counts as asked and the resolved request is
used). Outputs:
- ``results/metrics/solver_dev.json``: the weight grid and selection, results by label,
  statuses, validity, optimality, pool expansions, the comparison with E0 (gold input),
  and the agreement with the Phase 4 checker (labels, minimum costs, suggested budgets);
- ``results/predictions/solver_dev_gold_input.jsonl``: one row per scenario with the
  basket, statuses, solver log, trace and explanation;
- ``results/metrics/solver_latency_dev.json``: wall-clock times (machine-dependent, not
  part of ``--check``).
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from smartcart.data.contracts import load_catalog  # noqa: E402
from smartcart.optimization.cpsat import minimum_cost  # noqa: E402
from smartcart.pipeline.constrained import run_scenario, score_scenario  # noqa: E402
from smartcart.validation.feasibility import check_feasibility  # noqa: E402

LATENCY = "results/metrics/solver_latency_dev.json"
E0_METRICS = "results/metrics/E0_basket_dev.json"


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n"


def jsonl_text(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)


def reference(scenario: dict) -> dict:
    return scenario["resolved_request"] if scenario["label"] == "clarification" else scenario["gold_request"]


def run_all(scenarios, catalog, config):
    runs = []
    for s in scenarios:
        result = run_scenario(s, catalog, config, mode="gold_input")
        runs.append((s, result, score_scenario(result, s, catalog)))
    return runs


def grid_row(runs, checker_min: dict) -> dict:
    ratios, surplus = [], []
    for s, result, score in runs:
        if score["reference_label"] == "feasible" and score["outcome_ok"]:
            minimum = checker_min[s["scenario_id"]]
            if minimum:
                ratios.append(result["basket"]["total_cost_minor"] / minimum)
            surplus.append(result["basket"]["objective"]["components"]["surplus"])
    return {"success": sum(score["success"] for _, _, score in runs),
            "cost_ratio": round(statistics.mean(ratios), 6) if ratios else None,
            "surplus_share": round(statistics.mean(surplus), 6) if surplus else None}


def summarize(runs) -> dict:
    by_label = {}
    for label in ("feasible", "infeasible", "clarification"):
        rows = [(s, r, sc) for s, r, sc in runs if s["label"] == label]
        statuses = {}
        for _, r, _ in rows:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        by_label[label] = {"scenarios": len(rows), "success": sum(sc["success"] for _, _, sc in rows),
                           "success_rate": round(sum(sc["success"] for _, _, sc in rows) / len(rows), 6),
                           "statuses": dict(sorted(statuses.items()))}
    feasible_ref = [(s, r, sc) for s, r, sc in runs if sc["reference_label"] == "feasible"]
    valid = [(s, r, sc) for s, r, sc in runs if sc["labelled_valid"]]
    reasons = {}
    for _, r, _ in runs:
        key = f"{r['status']}:{r['basket']['reason']}"
        reasons[key] = reasons.get(key, 0) + 1
    lines = [line for _, r, _ in valid for line in r["basket"]["lines"]]
    return {
        "scenarios": len(runs),
        "success": sum(sc["success"] for _, _, sc in runs),
        "by_label": by_label,
        "valid_complete_success_feasible": by_label["feasible"]["success_rate"],
        "mean_coverage_feasible": round(statistics.mean(sc["coverage"] for s, _, sc in runs
                                                        if s["label"] == "feasible"), 6),
        "infeasible_detected": by_label["infeasible"]["success"],
        "false_rejections": sum(sc["false_rejection"] for _, _, sc in runs),
        "solver_timeouts": sum(sc["timeout"] for _, _, sc in runs),
        "outputs_labelled_valid": len(valid),
        "violations_among_valid": sum(sc["violation_among_valid"] for _, _, sc in runs),
        "optimality_proven_among_valid": sum(r["basket"]["reason"] == "optimal" for _, r, _ in valid),
        "feasible_reference_scenarios": len(feasible_ref),
        "status_reasons": dict(sorted(reasons.items())),
        "pool_expansions": sum(any(e["event"] == "expanded_to_catalog" for e in r["basket"]["trace"].get("events", []))
                               for _, r, _ in runs),
        "pair_variables": sum((r["basket"]["objective"] or {}).get("pair_variables", 0) for _, r, _ in runs),
        "lines_bought": len(lines),
        "lines_cheapest_option": sum(line["cheapest_option"] for line in lines),
        "has_history_subset": {"scenarios": sum(bool(s["has_history"]) for s, _, _ in runs),
                               "success": sum(sc["success"] for s, _, sc in runs if s["has_history"])},
    }


def checker_agreement(runs, catalog, config) -> dict:
    label_agree, min_agree, min_total, suggest_ok, suggest_total, rows = 0, 0, 0, 0, 0, []
    for s, result, _ in runs:
        ref = reference(s)
        checker = check_feasibility(ref, catalog)
        mine = {"valid": "feasible", "infeasible_in_scope": "infeasible"}.get(result["status"], result["status"])
        label_agree += mine == checker["label"]
        cpsat_min = minimum_cost(ref, catalog, config)
        min_total += 1
        min_agree += cpsat_min == checker.get("min_cost_minor")
        if result["basket"]["reason"] == "budget_below_minimum_cost":
            suggest_total += 1
            suggest_ok += result["basket"]["suggested_budget_minor"] == checker["min_cost_minor"]
        rows.append({"scenario_id": s["scenario_id"], "checker": checker["label"], "solver": mine,
                     "checker_min_cost_minor": checker.get("min_cost_minor"), "cpsat_min_cost_minor": cpsat_min})
    return {"label_agreement": label_agree, "min_cost_agreement": min_agree, "scenarios": min_total,
            "suggested_budget_equals_checker_minimum": suggest_ok, "budget_conflicts": suggest_total,
            "rows": rows}


def build(config: dict) -> tuple[dict, dict, dict, list]:
    if config["evaluated_splits"] != ["dev"]:
        raise SystemExit("Phase 9 evaluates dev only; the test scenarios are run in Phase 11")
    catalog = load_catalog(ROOT / config["data"]["catalog"])
    scenarios = json.loads((ROOT / config["data"]["basket_dev"]).read_text(encoding="utf-8"))
    if scenarios.get("split") != "dev":
        raise SystemExit("the basket file is not the dev split")
    scenarios = scenarios["scenarios"]
    checker_min = {s["scenario_id"]: check_feasibility(reference(s), catalog).get("min_cost_minor") for s in scenarios}
    grid = []
    for cost in config["grid"]["cost"]:
        for surplus in config["grid"]["surplus"]:
            trial = copy.deepcopy(config)
            trial["objective"]["weights"] = {"cost": cost, "surplus": surplus}
            grid.append({"cost": cost, "surplus": surplus, **grid_row(run_all(scenarios, catalog, trial), checker_min)})

    def key(i_row):
        i, row = i_row
        return (-row["success"], row["cost_ratio"] if row["cost_ratio"] is not None else float("inf"),
                row["surplus_share"] if row["surplus_share"] is not None else float("inf"), i)

    best = min(enumerate(grid), key=key)[1]
    selection = {"cost": best["cost"], "surplus": best["surplus"]}
    final = copy.deepcopy(config)
    final["objective"]["weights"] = selection
    runs = run_all(scenarios, catalog, final)
    e0 = json.loads((ROOT / E0_METRICS).read_text(encoding="utf-8"))["gold_input"]
    summary = summarize(runs)
    metrics = {
        "split": "dev", "mode": "gold_input", "selector": "CP-SAT (configs/solver.json)",
        "selection": {"rule": config["selection"]["rule"], "selected": selection, "grid": grid},
        "results": summary,
        "e0_gold_input": {"success": sum(v["success"] for v in e0["by_label"].values()),
                          "valid_complete_success_feasible": e0["valid_complete_success_feasible"],
                          "infeasible_detected": e0["infeasible_detected"],
                          "violations_among_valid": e0["violations_among_valid"],
                          "note": "E0 uses the Phase 1 TF-IDF text and top 10; read from " + E0_METRICS},
        "checker_agreement": checker_agreement(runs, catalog, final),
    }
    rows = []
    for s, r, sc in runs:
        basket = {k: v for k, v in r["basket"].items() if k != "timing"}
        rows.append({"scenario_id": s["scenario_id"], "label": s["label"], "design": s["design"],
                     "status": r["status"], "clarifications_asked": r["clarifications_asked"], "turns": r["turns"],
                     "basket": basket, "score": sc, "explanation": r["explanation"]})
    out = config["outputs"]
    files = {out["metrics"]: json_text(metrics), out["predictions"]: jsonl_text(rows)}
    timing = [r["basket"]["timing"] for _, r, _ in runs if r["basket"]["timing"]]
    return files, metrics, selection, timing


def latency(timing: list[dict]) -> dict:
    def stats(values):
        values = sorted(values)
        return {"p50": round(statistics.median(values), 4),
                "p95": round(values[min(len(values) - 1, int(0.95 * len(values)))], 4),
                "max": round(values[-1], 4)}
    return {"scenarios": len(timing), "selection_total_s": stats([t["total_s"] for t in timing]),
            "cpsat_solve_s": stats([t["solver_s"] for t in timing]),
            "note": "warm, machine-dependent; selection only (no parsing); not part of --check"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/solver.json")
    ap.add_argument("--select", action="store_true", help="freeze the selected weights")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config_path = ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    files, metrics, selection, timing = build(config)
    if args.select:
        config["selection"]["selected"] = selection
        config["objective"]["weights"] = selection
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                               newline="\n")
        print("frozen weights:", selection)
    elif selection != config["selection"]["selected"] or selection != config["objective"]["weights"]:
        raise SystemExit(f"selection {selection} differs from the frozen config; run --select on purpose")
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    (ROOT / LATENCY).write_text(json_text(latency(timing)), encoding="utf-8", newline="\n")
    r = metrics["results"]
    a = metrics["checker_agreement"]
    print(f"success {r['success']}/{r['scenarios']}  feasible {r['by_label']['feasible']['success']}/"
          f"{r['by_label']['feasible']['scenarios']}  infeasible detected {r['infeasible_detected']}  "
          f"violations among valid {r['violations_among_valid']}")
    print(f"checker agreement: labels {a['label_agreement']}/{a['scenarios']}, minimum cost "
          f"{a['min_cost_agreement']}/{a['scenarios']}, suggested budgets "
          f"{a['suggested_budget_equals_checker_minimum']}/{a['budget_conflicts']}")
    print("weights:", selection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
