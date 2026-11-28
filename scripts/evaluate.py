"""Run one Phase 11 experiment configuration on the basket benchmark (D9).

Usage:
    python scripts/evaluate.py --config configs/experiments/E3.json             # the test split (frozen)
    python scripts/evaluate.py --config configs/experiments/E3.json --check     # rebuild and compare
    python scripts/evaluate.py --config configs/experiments/E3.json --split dev # development sanity run

Both modes run: ``gold_input`` (component-isolated, the gold StructuredRequest) and
``end_to_end`` (the run's parser; every seed for the transformer). On the test split the
locked files are checked against ``docs/benchmark_lock.md`` before anything is read.

Outputs (test split):
- ``results/predictions/runs/<RUN>_<mode>[_seed<N>].jsonl``: one row per scenario with
  the extracted constraints, the candidates, the selected products and packs, the total,
  the status, the solver log and the score against the gold request;
- ``results/metrics/runs/<RUN>.json``: metrics per mode (and per seed, with mean and
  spread);
- ``results/metrics/runs/<RUN>_latency.json``: cold load and warm per-scenario latency
  (machine-dependent, not part of ``--check``).
A dev run writes the same files under the ignored ``data/interim/phase11_dev/``.
"""

from __future__ import annotations

import time

START = time.perf_counter()

import argparse  # noqa: E402
import gc  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from smartcart.data.contracts import load_catalog  # noqa: E402
from smartcart.pipeline.experiment import (  # noqa: E402
    across_seeds, json_text, jsonl_text, row, run_scenario, run_settings, score, summarize, verify_lock,
)


def load_parser(kind: str, catalog: dict, seed):
    from smartcart.nlu import api

    if kind == "baseline":
        return api.get_parser(catalog, "baseline")
    config = json.loads(api.TRANSFORMER_CONFIG.read_text(encoding="utf-8"))
    return api.load_transformer_parser(catalog, config, seed, ROOT)


def warm_retrieval(catalog: dict, settings: dict) -> None:
    from smartcart.retrieval.api import retrieve_candidates

    r = settings["retrieval"]
    retrieve_candidates(catalog["ingredients"][0]["id"], catalog, method=r["method"], top_k=1,
                        product_text=r["product_text"])


def output_paths(evaluation: dict, split: str) -> dict:
    out = dict(evaluation["outputs"])
    if split != "test":
        base = evaluation["outputs"]["dev_sanity"]
        for key in ("rows", "run_metrics", "run_latency"):
            out[key] = f"{base}/{Path(out[key]).name}"
    return out


def stats(values: list[float]) -> dict:
    values = sorted(values)
    return {"n": len(values), "p50": round(statistics.median(values), 4),
            "p95": round(values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))], 4),
            "max": round(values[-1], 4)}


def run_mode(scenarios, catalog, settings, parser, mode, seed):
    rows, latency = [], []
    for s in scenarios:
        t0 = time.perf_counter()
        result = run_scenario(s, catalog, settings, parser=parser, mode=mode)
        latency.append(time.perf_counter() - t0)
        scored = score(result, s, catalog, settings["selection"])
        rows.append(row(s, result, scored, catalog, settings, mode, seed))
    return rows, latency


def build(run_config: dict, evaluation: dict, split: str, seeds_override=None) -> tuple[dict, dict, dict]:
    solver = json.loads((ROOT / evaluation["solver_config"]).read_text(encoding="utf-8"))
    settings = run_settings(run_config, solver)
    if split == "test":
        lock = verify_lock(ROOT, ROOT / evaluation["lock"])
        if not all(lock.values()):
            raise SystemExit(f"locked files changed, refusing to evaluate: {lock}")
    catalog = load_catalog(ROOT / evaluation["data"]["catalog"])
    data = json.loads((ROOT / evaluation["data"]["basket"][split]).read_text(encoding="utf-8"))
    if data.get("split") != split:
        raise SystemExit(f"the basket file is not the {split} split")
    scenarios = data["scenarios"]
    seeds = [None] if settings["parser"] == "baseline" else list(seeds_override or evaluation["seeds"])
    out = output_paths(evaluation, split)
    files, latency = {}, {}

    parser = load_parser(settings["parser"], catalog, seeds[0])
    warm_retrieval(catalog, settings)
    latency["cold_load_s"] = round(time.perf_counter() - START, 3)

    gold_rows, gold_lat = run_mode(scenarios, catalog, settings, None, "gold_input", None)
    files[out["rows"].format(run=settings["run"], mode="gold_input", seed="")] = jsonl_text(gold_rows)
    latency["gold_input"] = stats(gold_lat)
    metrics = {"run": settings["run"], "split": split, "description": run_config["description"],
               "settings": {k: v for k, v in settings.items() if k != "solver"},
               "gold_input": summarize(gold_rows)}

    per_seed, e2e_lat = {}, []
    for i, seed in enumerate(seeds):
        if i > 0:
            del parser
            gc.collect()
            parser = load_parser(settings["parser"], catalog, seed)
        rows, lat = run_mode(scenarios, catalog, settings, parser, "end_to_end", seed)
        suffix = "" if seed is None else f"_seed{seed}"
        files[out["rows"].format(run=settings["run"], mode="end_to_end", seed=suffix)] = jsonl_text(rows)
        per_seed["single" if seed is None else str(seed)] = summarize(rows)
        e2e_lat.extend(lat)
    metrics["end_to_end"] = {"seeds": [s for s in seeds if s is not None] or None, "per_seed": per_seed}
    if len(per_seed) > 1:
        metrics["end_to_end"]["across_seeds"] = across_seeds(per_seed)
    latency["end_to_end"] = stats(e2e_lat)
    latency["note"] = ("machine-dependent; not part of --check. cold_load_s runs from process start to the first "
                       "parser and retrieval index being ready; per-scenario times include parsing, the "
                       "clarification dialogue and selection")
    files[out["run_metrics"].format(run=settings["run"])] = json_text(metrics)
    return files, metrics, {"path": out["run_latency"].format(run=settings["run"]), "record": latency}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--evaluation", default="configs/experiments/evaluation.json")
    ap.add_argument("--split", choices=["test", "dev"], default=None)
    ap.add_argument("--seeds", type=int, nargs="*", help="development only: fewer seeds")
    ap.add_argument("--dev-parser", choices=["baseline"], help="development only: replace the run's parser")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    evaluation = json.loads((ROOT / args.evaluation).read_text(encoding="utf-8"))
    run_config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    split = args.split or evaluation["split"]
    if (args.seeds or args.dev_parser) and split == "test":
        raise SystemExit("--seeds and --dev-parser are for development runs on dev only")
    if args.dev_parser:
        run_config = {**run_config, "parser": {"type": args.dev_parser}}
    files, metrics, latency = build(run_config, evaluation, split, args.seeds)
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    (ROOT / latency["path"]).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / latency["path"]).write_text(json_text(latency["record"]), encoding="utf-8", newline="\n")
    g = metrics["gold_input"]
    print(f"{metrics['run']} [{split}] gold_input: success {g['success']}/{g['scenarios']}, feasible "
          f"{g['feasible']['success']}/{g['feasible']['scenarios']}, infeasible {g['infeasible']['detected']}/"
          f"{g['infeasible']['scenarios']}, violations {g['violations_among_valid']}")
    for seed, m in metrics["end_to_end"]["per_seed"].items():
        print(f"{metrics['run']} [{split}] end_to_end seed {seed}: success {m['success']}/{m['scenarios']}, feasible "
              f"{m['feasible']['success']}/{m['feasible']['scenarios']}, infeasible {m['infeasible']['detected']}/"
              f"{m['infeasible']['scenarios']}, clarification {m['clarification']['success_within_turns']}/"
              f"{m['clarification']['scenarios']}, violations {m['violations_among_valid']}")
    print(f"cold load {latency['record']['cold_load_s']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
