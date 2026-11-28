"""Phase 11 report tables, bootstrap intervals and figures (D9).

Usage:
    python scripts/make_report.py            # from the test-split outputs
    python scripts/make_report.py --check    # rebuild the summary and tables in memory and compare
    python scripts/make_report.py --split dev

Reads ``results/metrics/runs/<RUN>.json`` and the rows in ``results/predictions/runs/``
(made by ``scripts/evaluate.py``) and ``results/metrics/test_components.json`` (made by
``scripts/evaluate_components.py``). Writes:
- ``results/metrics/phase11_summary.json``: every number in the tables, plus paired
  bootstrap intervals over scenario families for the planned comparisons;
- ``results/tables/*.md``: one table per report section (``latency.md`` is
  machine-dependent and not part of ``--check``);
- figures 14–18 (not part of ``--check``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.pipeline.experiment import family_bootstrap, json_text  # noqa: E402

MODES = ("gold_input", "end_to_end")
DEV_REFERENCE = {"nlu_e0": "results/metrics/E0_nlu_dev.json", "nlu": "results/metrics/nlu_dev.json",
                 "retrieval": "results/metrics/retrieval_dev.json", "trackb": "results/metrics/trackb_validation.json"}


def paths(evaluation: dict, split: str) -> dict:
    out = dict(evaluation["outputs"])
    if split != "test":
        for key in ("rows", "run_metrics", "run_latency", "components"):
            out[key] = f"{evaluation['outputs']['dev_sanity']}/{Path(out[key]).name}"
        out["summary"] = f"{evaluation['outputs']['dev_sanity']}/phase11_summary.json"
        out["tables"] = f"{evaluation['outputs']['dev_sanity']}/tables"
    return out


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def success_by_scenario(out: dict, run: str, mode: str, seeds) -> dict[str, float]:
    """Scenario success; the mean over seeds for multi-seed end-to-end runs."""
    if mode == "gold_input" or not seeds:
        rows = read_rows(ROOT / out["rows"].format(run=run, mode=mode, seed=""))
        return {r["scenario_id"]: float(r["score"]["success"]) for r in rows}
    per_seed = [read_rows(ROOT / out["rows"].format(run=run, mode=mode, seed=f"_seed{s}")) for s in seeds]
    ids = [r["scenario_id"] for r in per_seed[0]]
    return {sid: sum(float(rows[i]["score"]["success"]) for rows in per_seed) / len(per_seed)
            for i, sid in enumerate(ids)}


def mode_view(metrics: dict, mode: str) -> dict:
    """Headline numbers for one run and mode (means over seeds where there are several)."""
    if mode == "gold_input":
        m = metrics["gold_input"]
        return {"seeds": None, **_headline(m)}
    per_seed = metrics["end_to_end"]["per_seed"]
    views = [_headline(m) for m in per_seed.values()]
    if len(views) == 1:
        return {"seeds": None, **views[0]}
    out = {"seeds": list(per_seed)}
    for key in views[0]:
        values = [v[key] for v in views]
        if all(isinstance(v, (int, float)) for v in values):
            mean = sum(values) / len(values)
            out[key] = round(mean, 6)
            out[f"{key}_min"], out[f"{key}_max"] = min(values), max(values)
        else:
            out[key] = values[0]
    return out


def _headline(m: dict) -> dict:
    return {"scenarios": m["scenarios"], "success": m["success"],
            "feasible_success": m["feasible"]["success"], "feasible": m["feasible"]["scenarios"],
            "valid_complete_success_feasible": m["valid_complete_success_feasible"],
            "mean_coverage_feasible": m["mean_coverage_feasible"],
            "outputs_labelled_valid": m["outputs_labelled_valid"],
            "violations_among_valid": m["violations_among_valid"],
            "infeasible_detected": m["infeasible"]["detected"], "infeasible": m["infeasible"]["scenarios"],
            "false_rejections": m["false_rejections"],
            "clarification_success": m["clarification"]["success_within_turns"],
            "clarification": m["clarification"]["scenarios"],
            "unnecessary_clarifications": m["unnecessary_clarifications"], "solver_timeouts": m["solver_timeouts"]}


def fmt(v, digits=3):
    return "n/a" if v is None else (f"{v:.{digits}f}" if isinstance(v, float) else str(v))


def spread(view: dict, key: str, digits=1) -> str:
    v = view[key]
    if f"{key}_min" in view and view[f"{key}_min"] != view[f"{key}_max"]:
        return f"{v:.{digits}f} ({view[f'{key}_min']}–{view[f'{key}_max']})"
    return f"{v:.{digits}f}" if isinstance(v, float) and v != int(v) else str(int(v) if isinstance(v, float) else v)


def build(evaluation: dict, split: str) -> tuple[dict, dict, dict]:
    out = paths(evaluation, split)
    runs = {}
    for run in evaluation["runs"]:
        runs[run] = json.loads((ROOT / out["run_metrics"].format(run=run)).read_text(encoding="utf-8"))
    components = json.loads((ROOT / out["components"]).read_text(encoding="utf-8"))
    families = {}
    for r in read_rows(ROOT / out["rows"].format(run="E0", mode="gold_input", seed="")):
        families[r["scenario_id"]] = r["family_id"]
    views = {run: {mode: mode_view(m, mode) for mode in MODES} for run, m in runs.items()}
    boot = evaluation["bootstrap"]
    comparisons = {}
    for a, b in evaluation["comparisons"]:
        comparisons[f"{a} - {b}"] = {}
        for mode in MODES:
            sa = success_by_scenario(out, a, mode, runs[a]["end_to_end"]["seeds"])
            sb = success_by_scenario(out, b, mode, runs[b]["end_to_end"]["seeds"])
            comparisons[f"{a} - {b}"][mode] = family_bootstrap(sa, sb, families, boot["resamples"], boot["seed"])
    run_views = {run: {"description": runs[run]["description"], "settings": runs[run]["settings"], **views[run]}
                 for run in runs}
    summary = {"split": split, "runs": run_views, "comparisons": comparisons, "components": components}
    tables = make_tables(summary, evaluation)
    files = {out["summary"]: json_text(summary)}
    for name, text in tables.items():
        files[f"{out['tables']}/{name}.md"] = text
    latency = {run: json.loads((ROOT / out["run_latency"].format(run=run)).read_text(encoding="utf-8"))
               for run in runs if (ROOT / out["run_latency"].format(run=run)).exists()}
    return files, summary, latency


def make_tables(summary: dict, evaluation: dict) -> dict[str, str]:
    split = summary["split"]
    t = {}
    c = summary["components"]
    # ---- NLU
    nlu = c["nlu"]
    lines = [f"# NLU on the {split} split ({nlu['examples']} examples)", "",
             "| Parser | Intent macro-F1 (classifier only) | Intent macro-F1 | Slot micro-F1 | Request exact match |",
             "| --- | --- | --- | --- | --- |"]
    b = nlu["baseline_summary"]
    lines.append(f"| E0 baseline | {fmt(b['intent_macro_f1_classifier_only'])} | {fmt(b['intent_macro_f1'])} | "
                 f"{fmt(b['slot_micro_f1'])} | {fmt(b['request_exact_match'])} |")
    if "transformer" in nlu:
        s = nlu["transformer"]["summary"]
        keys = ("intent_macro_f1_classifier_only", "intent_macro_f1", "slot_micro_f1", "request_exact_match")
        cells = " | ".join(f"{s[k]['mean']:.3f} ± {s[k]['std']:.3f}" for k in keys)
        lines.append(f"| DistilBERT (mean ± std, 3 seeds) | {cells} |")
    lines += ["", "Command: `python scripts/evaluate_components.py` (config `configs/experiments/evaluation.json`)."]
    t["nlu"] = "\n".join(lines) + "\n"
    # ---- retrieval
    r = c["retrieval"]
    types = sorted(r["minilm"]["by_query_type"])
    lines = [f"# Retrieval on the {split} split ({r['queries']} queries)", "",
             "| Setting | Recall@5 | Recall@10 | MRR | " + " | ".join(f"R@10 {ty}" for ty in types) + " |",
             "| --- | --- | --- | --- | " + " | ".join("---" for _ in types) + " |"]
    for name in ("tfidf_legacy_top10", "tfidf", "minilm"):
        x = r[name]
        lines.append(f"| {name} ({x['method']}, {x['product_text']}) | {fmt(x['recall_at_5'])} | "
                     f"{fmt(x['recall_at_10'])} | {fmt(x['mrr'])} | " +
                     " | ".join(f"{fmt(x['by_query_type'][ty]['recall_at_10'])}" for ty in types) + " |")
    lines += ["", "Command: `python scripts/evaluate_components.py`."]
    t["retrieval"] = "\n".join(lines) + "\n"
    # ---- baskets
    lines = [f"# Basket benchmark, {split} split", "",
             "Feasible success = labelled valid and valid against the gold request. Multi-seed end-to-end runs show "
             "the mean over 3 seeds (min–max).", "",
             "| Run | Mode | Feasible success | Coverage | Valid outputs / violations | Infeasible detected | "
             "False rejections | Clarification success | Unnecessary questions | Timeouts |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for run, view in summary["runs"].items():
        for mode in MODES:
            v = view[mode]
            lines.append(f"| {run} | {mode} | {spread(v, 'feasible_success')} / {v['feasible']} | "
                         f"{fmt(v['mean_coverage_feasible'])} | {spread(v, 'outputs_labelled_valid')} / "
                         f"{spread(v, 'violations_among_valid')} | {spread(v, 'infeasible_detected')} / "
                         f"{v['infeasible']} | {spread(v, 'false_rejections')} | "
                         f"{spread(v, 'clarification_success')} / {v['clarification']} | "
                         f"{spread(v, 'unnecessary_clarifications')} | {spread(v, 'solver_timeouts')} |")
    lines += ["", "Command per run: `python scripts/evaluate.py --config configs/experiments/<RUN>.json`."]
    t["baskets"] = "\n".join(lines) + "\n"
    # ---- comparisons
    lines = [f"# Paired comparisons ({split}): difference in scenario success, 95% bootstrap interval over families",
             "", "| Comparison | gold_input | end_to_end |", "| --- | --- | --- |"]
    for name, modes in summary["comparisons"].items():
        cells = [f"{m['difference']:+.3f} [{m['ci95'][0]:+.3f}, {m['ci95'][1]:+.3f}]" for m in
                 (modes["gold_input"], modes["end_to_end"])]
        lines.append(f"| {name} | {cells[0]} | {cells[1]} |")
    fam = next(iter(summary["comparisons"].values()))["gold_input"]
    lines += ["", f"{fam['families']} families, {fam['scenarios']} scenarios, {fam['resamples']} resamples "
              f"(seed {evaluation['bootstrap']['seed']}). Command: `python scripts/make_report.py`."]
    t["comparisons"] = "\n".join(lines) + "\n"
    # ---- Track B
    tb = c["track_b"]
    lines = [f"# Track B ({tb['target']}; history {', '.join(tb['history'])}; rules from training orders)", "",
             f"Users: {tb['users']['evaluated']} evaluated, {tb['users']['excluded_empty_target']} excluded "
             "(no mapped ingredient in the target order).", "",
             "| Ranker | Recall@10 | NDCG@10 | Repeat R@10 | Repeat NDCG@10 | New R@10 | New NDCG@10 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for ranker, res in tb["results"].items():
        lines.append(f"| {ranker} | {fmt(res['all']['recall_at_10'])} | {fmt(res['all']['ndcg_at_10'])} | "
                     f"{fmt(res['repeat']['recall_at_10'])} | {fmt(res['repeat']['ndcg_at_10'])} | "
                     f"{fmt(res['new']['recall_at_10'])} | {fmt(res['new']['ndcg_at_10'])} |")
    lines += ["", "| Paired bootstrap (users) | Mean difference | 95% interval |", "| --- | --- | --- |"]
    for name, bs in tb["bootstrap"].items():
        lines.append(f"| {name} | {bs['mean_difference']:+.4f} | [{bs['ci95'][0]:+.4f}, {bs['ci95'][1]:+.4f}] |")
    lines += ["", "Command: `python scripts/evaluate_components.py`."]
    t["track_b"] = "\n".join(lines) + "\n"
    return t


def latency_table(latency: dict, split: str) -> str:
    lines = [f"# Latency ({split}; machine-dependent, not part of --check)", "",
             "| Run | Cold load (s) | gold_input p50 / p95 (s) | end_to_end p50 / p95 (s) |",
             "| --- | --- | --- | --- |"]
    for run, x in latency.items():
        lines.append(f"| {run} | {x['cold_load_s']} | {x['gold_input']['p50']} / {x['gold_input']['p95']} | "
                     f"{x['end_to_end']['p50']} / {x['end_to_end']['p95']} |")
    return "\n".join(lines) + "\n"


def figures(summary: dict, latency: dict, evaluation: dict, dev_refs: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    figs = evaluation["outputs"]["figures"]
    runs = list(summary["runs"])
    c = summary["components"]
    # 14: parser errors (dev vs test)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    keys = [("intent_macro_f1_classifier_only", "Intent F1\n(classifier)"), ("intent_macro_f1", "Intent F1"),
            ("slot_micro_f1", "Slot F1"), ("request_exact_match", "Exact match")]
    series = [("E0 baseline, dev", [dev_refs["nlu_e0"][k] for k, _ in keys]),
              ("E0 baseline, test", [c["nlu"]["baseline_summary"][k] for k, _ in keys])]
    if "transformer" in c["nlu"]:
        series += [("DistilBERT, dev", [dev_refs["nlu_tf"][k] for k, _ in keys]),
                   ("DistilBERT, test", [c["nlu"]["transformer"]["summary"][k]["mean"] for k, _ in keys])]
    x = np.arange(len(keys))
    w = 0.8 / len(series)
    for i, (label, vals) in enumerate(series):
        bars = ax.bar(x + (i - (len(series) - 1) / 2) * w, vals, w, label=label)
        ax.bar_label(bars, fmt="%.2f", fontsize=7)
    ax.set_xticks(x, [k for _, k in keys])
    ax.set_ylim(0, 1.1)
    ax.legend(fontsize=8, ncol=2)
    ax.set_title("Parser quality: validation vs held-out test templates (DistilBERT = mean of 3 seeds)", fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / figs["parser_errors"], dpi=150, metadata={"Software": None})
    plt.close(fig)
    # 15: retrieval
    r = c["retrieval"]
    names = ["tfidf_legacy_top10", "tfidf", "minilm"]
    types = sorted(r["minilm"]["by_query_type"])
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    mk = [("recall_at_5", "Recall@5"), ("recall_at_10", "Recall@10"), ("mrr", "MRR")]
    x = np.arange(len(mk))
    for i, name in enumerate(names):
        bars = axes[0].bar(x + (i - 1) * 0.27, [r[name][k] for k, _ in mk], 0.27, label=name)
        axes[0].bar_label(bars, fmt="%.2f", fontsize=7)
    axes[0].set_xticks(x, [m for _, m in mk])
    axes[0].set_ylim(0, 1.05)
    axes[0].legend(fontsize=8)
    axes[0].set_title(f"Retrieval, {r['queries']} {summary['split']} queries", fontsize=10)
    xt = np.arange(len(types))
    for i, name in enumerate(names):
        axes[1].bar(xt + (i - 1) * 0.27, [r[name]["by_query_type"][ty]["recall_at_10"] for ty in types], 0.27,
                    label=name)
    counts = [r["minilm"]["by_query_type"][ty]["num_queries"] for ty in types]
    axes[1].set_xticks(xt, [f"{ty}\n(n={n})" for ty, n in zip(types, counts)], fontsize=8)
    axes[1].set_ylim(0, 1.05)
    axes[1].set_title("Recall@10 by query type", fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / figs["retrieval"], dpi=150, metadata={"Software": None})
    plt.close(fig)
    # 16: basket success and validity
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=True)
    parts = [("feasible_success", "feasible", "Feasible: valid complete success"),
             ("infeasible_detected", "infeasible", "Infeasible: detected"),
             ("clarification_success", "clarification", "Clarification: success within 3 turns")]
    x = np.arange(len(runs))
    for ax, (key, den, title) in zip(axes, parts):
        for j, mode in enumerate(MODES):
            vals = [summary["runs"][run][mode][key] / summary["runs"][run][mode][den] for run in runs]
            ax.bar(x + (j - 0.5) * 0.38, vals, 0.38, label=mode)
        ax.set_xticks(x, runs, fontsize=8)
        ax.set_ylim(0, 1.05)
        ax.set_title(title, fontsize=10)
    axes[0].legend(fontsize=8)
    violations = sum(summary["runs"][run][m]["violations_among_valid"] for run in runs for m in MODES)
    fig.suptitle(f"Basket benchmark ({summary['split']}); violations among outputs labelled valid, all runs and "
                 f"modes: {violations:g}", fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / figs["baskets"], dpi=150, metadata={"Software": None})
    plt.close(fig)
    # 17: ablations / comparisons
    comps = list(summary["comparisons"])
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(comps) + 1.6))
    y = np.arange(len(comps))
    for j, mode in enumerate(MODES):
        d = [summary["comparisons"][k][mode]["difference"] for k in comps]
        lo = [d[i] - summary["comparisons"][k][mode]["ci95"][0] for i, k in enumerate(comps)]
        hi = [summary["comparisons"][k][mode]["ci95"][1] - d[i] for i, k in enumerate(comps)]
        ax.errorbar(d, y + (j - 0.5) * 0.3, xerr=[lo, hi], fmt="o", capsize=3, label=mode)
    ax.axvline(0, color="grey", linewidth=1)
    ax.set_yticks(y, comps)
    ax.invert_yaxis()
    ax.set_xlabel("difference in scenario success (95% bootstrap interval over families)")
    ax.legend(fontsize=8)
    ax.set_title(f"Planned comparisons and ablations ({summary['split']})", fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / figs["ablations"], dpi=150, metadata={"Software": None})
    plt.close(fig)
    # 18: latency
    if latency:
        lr = [run for run in runs if run in latency]
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
        x = np.arange(len(lr))
        for j, (k, label) in enumerate((("p50", "p50"), ("p95", "p95"))):
            axes[0].bar(x + (j - 0.5) * 0.38, [latency[run]["end_to_end"][k] for run in lr], 0.38, label=label)
        axes[0].set_xticks(x, lr)
        axes[0].set_ylabel("seconds per scenario (end to end)")
        axes[0].axhline(5, color="red", linewidth=1, linestyle="--")
        axes[0].text(0, 5, " 5 s target", color="red", fontsize=8, va="bottom")
        axes[0].legend(fontsize=8)
        axes[0].set_title("Warm latency per scenario", fontsize=10)
        axes[1].bar(x, [latency[run]["cold_load_s"] for run in lr], color="#888888")
        axes[1].set_xticks(x, lr)
        axes[1].set_ylabel("seconds")
        axes[1].set_title("Cold load (process start to parser and index ready)", fontsize=10)
        fig.tight_layout()
        fig.savefig(ROOT / figs["latency"], dpi=150, metadata={"Software": None})
        plt.close(fig)


def dev_references() -> dict:
    e0 = json.loads((ROOT / DEV_REFERENCE["nlu_e0"]).read_text(encoding="utf-8"))
    refs = {"nlu_e0": {"intent_macro_f1_classifier_only": e0["intent_classifier_only"]["macro_f1"],
                       "intent_macro_f1": e0["intent"]["macro_f1"], "slot_micro_f1": e0["slots"]["micro"]["f1"],
                       "request_exact_match": e0["request_exact_match"]["accuracy"]}}
    nlu = json.loads((ROOT / DEV_REFERENCE["nlu"]).read_text(encoding="utf-8"))
    tf = nlu.get("transformer", {}).get("summary", {})
    keymap = {"intent_macro_f1_classifier_only": "intent_macro_f1_classifier",
              "intent_macro_f1": "intent_macro_f1", "slot_micro_f1": "slot_micro_f1",
              "request_exact_match": "request_exact_match"}
    refs["nlu_tf"] = {k: tf[v]["mean"] for k, v in keymap.items() if v in tf}
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evaluation", default="configs/experiments/evaluation.json")
    ap.add_argument("--split", choices=["test", "dev"], default=None)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    evaluation = json.loads((ROOT / args.evaluation).read_text(encoding="utf-8"))
    split = args.split or evaluation["split"]
    files, summary, latency = build(evaluation, split)
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    tables_dir = Path(paths(evaluation, split)["tables"])
    (ROOT / tables_dir / "latency.md").write_text(latency_table(latency, split), encoding="utf-8", newline="\n")
    if split == "test":
        figures(summary, latency, evaluation, dev_references())
    for name in ("baskets", "comparisons"):
        print(files[f"{tables_dir.as_posix()}/{name}.md"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
