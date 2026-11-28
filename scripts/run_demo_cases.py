"""Run the six Phase 10 demo cases through the interface logic (Phase 10).

Usage:
    python scripts/run_demo_cases.py            # run the cases and write the record
    python scripts/run_demo_cases.py --check    # rebuild the record in memory and compare

Each case in ``configs/app.json`` is a short conversation (parse, answer, confirm a
recipe, edit, revise). The cases go through ``smartcart.app.session``, the same
functions ``app.py`` calls, with the app's configured parser (DistilBERT, or the E0
baseline when the checkpoints are missing). The record keeps, per step: the extracted
fields, any clarification question and suggestions, the status, the basket total, the
explanation summary, "what changed", and the CSV and JSON exports' sizes. Each case is
marked as working only if its expectations hold. Output:
``results/metrics/demo_cases.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from smartcart.app import session as S  # noqa: E402


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n"


def step_record(action: str, request: dict, record: dict | None, extra: dict | None = None) -> dict:
    out = {"action": action, "fields": {k: v for k, v in S.request_fields(request).items() if v is not None},
           "needs_clarification": request["needs_clarification"],
           "clarification_type": request.get("clarification_type"),
           "clarification_prompt": request.get("clarification_prompt")}
    if record is not None:
        result = record["result"]
        out.update(status=result["status"], status_label=S.status_view(result)[0], reason=result["reason"],
                   total_cost_minor=result["total_cost_minor"] if result["status"] == "valid" else None,
                   suggested_budget_minor=result.get("suggested_budget_minor"),
                   products=[line["product_id"] for line in result.get("lines", [])],
                   summary=record["explanation"]["summary"],
                   export_csv_rows=S.export_csv(result).count("\n") - 2,
                   export_json_ok=bool(json.loads(S.export_json(record))["result"]))
    out.update(extra or {})
    return out


def run_case(case: dict, parser: str) -> dict:
    request, record, steps, changes = None, None, [], []
    for step in case["steps"]:
        action, extra = step["action"], {}
        previous = record
        if action == "parse":
            user = S.history_users()[0] if step.get("user_id") == "first_listed" else None
            request = S.parse(step["text"], parser, user)
            extra = {"text": step["text"], "user_id": user}
        elif action == "answer":
            request = S.answer(request, step["text"], parser)
            extra = {"text": step["text"]}
        elif action == "revise":
            request = S.revise(record["request"], step["text"], parser)
            extra = {"text": step["text"]}
        elif action == "confirm_recipe":
            suggestions = S.recipe_suggestions(request)
            extra = {"suggestions": [name for _, name in suggestions]}
            if not suggestions:
                steps.append(step_record(action, request, None, {**extra, "error": "no suggestion"}))
                break
            request = S.confirm_recipe(request, suggestions[0][0], parser)
            extra["chosen"] = suggestions[0][1]
        elif action == "edit":
            lines = record["result"].get("lines", [])
            target = max(lines, key=lambda line: (line["line_cost_minor"], line["ingredient_id"]))["ingredient_id"]
            request = S.edit(record["request"], exclusions=list(record["request"].get("exclusions") or []) + [target])
            extra = {"excluded": target}
        else:
            raise ValueError(action)
        record = None if request["needs_clarification"] else S.run(request)
        if record is not None and previous is not None and action in {"revise", "edit"}:
            changes = S.changes(previous, record)
            extra["changes"] = changes
        steps.append(step_record(action, request, record, extra))
    final = steps[-1]
    expect = case["expect"]
    checks = {"final_status": final.get("status") == expect["final_status"]}
    if "changes_mention" in expect:
        checks["changes_mention"] = any(expect["changes_mention"] in c.lower() for c in changes)
    if expect.get("pantry_used"):
        checks["pantry_used"] = bool(record and record["request"]["pantry"]
                                     and all(v is not None for v in record["request"]["pantry"].values()))
    if expect.get("suggested_budget"):
        checks["suggested_budget"] = final.get("suggested_budget_minor") is not None
    return {"id": case["id"], "title": case["title"], "steps": steps, "expected": expect, "checks": checks,
            "works": all(checks.values())}


def build(config: dict, parser_name: str | None) -> tuple[dict, dict]:
    parser, note = S.choose_parser(parser_name)
    cases = [run_case(case, parser) for case in config["demo_cases"]]
    record = {"parser": parser, "parser_note": note, "price_note": S.BANNER,
              "cases_working": sum(c["works"] for c in cases), "cases": cases}
    return {config["outputs"]["demo_cases"]: json_text(record)}, record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/app.json")
    ap.add_argument("--parser", choices=["transformer", "baseline"], default=None)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    files, record = build(config, args.parser)
    if args.check:
        bad = [p for p, text in files.items()
               if not (ROOT / p).exists() or (ROOT / p).read_text(encoding="utf-8") != text]
        for p in files:
            print(("DIFFERS " if p in bad else "same    ") + p)
        return 1 if bad else 0
    for path, text in files.items():
        (ROOT / path).write_text(text, encoding="utf-8", newline="\n")
    for case in record["cases"]:
        last = case["steps"][-1]
        mark = "OK " if case["works"] else "NO "
        print(f"{mark} {case['id']:24s} {last.get('status')}  {last.get('summary', '')[:90]}")
    print(f"{record['cases_working']}/{len(record['cases'])} demo cases work (parser: {record['parser']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
