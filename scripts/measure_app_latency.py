"""Measure the interface's cold-load and warm latency (Phase 10).

Usage:
    python scripts/measure_app_latency.py

Runs ``app.py`` headless with Streamlit's ``AppTest`` in this (fresh) process:

- **cold load**: from process start to the first rendered page, which loads the parser,
  the catalog and the MiniLM index (the app's cached warm-up);
- **warm request**: submitting each demo case's first message, timed per submission
  (parse + constrained selection + validation + explanations + rendering), repeated;
- **warm selection only**: ``session.run`` on the parsed requests.

Machine-dependent; the file is not part of any ``--check``. Output:
``results/metrics/app_latency.json``.
"""

from __future__ import annotations

import time

START = time.perf_counter()

import json  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

REPEATS = 3
SUBMIT = "FormSubmitter:request_form-Plan my basket"


def stats(values: list[float]) -> dict:
    values = sorted(values)
    return {"n": len(values), "p50": round(statistics.median(values), 3),
            "p95": round(values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))], 3),
            "max": round(values[-1], 3)}


def main() -> int:
    from streamlit.testing.v1 import AppTest

    from smartcart.app import session as S

    config = S.config()
    parser, note = S.choose_parser()
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=600)
    app.run()
    cold = time.perf_counter() - START
    if app.exception:
        raise SystemExit(f"the app raised: {app.exception}")
    texts = [case["steps"][0]["text"] for case in config["demo_cases"]]
    warm = []
    for _ in range(REPEATS):
        for text in texts:
            app.text_area(key="request_text").set_value(text)
            t0 = time.perf_counter()
            app.button(key=SUBMIT).click().run()
            warm.append(time.perf_counter() - t0)
            if app.exception:
                raise SystemExit(f"the app raised: {app.exception}")
    selection = []
    for text in texts:
        request = S.parse(text, parser)
        if request["needs_clarification"]:
            continue
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            S.run(request)
            selection.append(time.perf_counter() - t0)
    record = {
        "parser": parser, "parser_note": note,
        "machine": {"platform": platform.platform(), "python": platform.python_version(),
                    "cpu_count": os.cpu_count()},
        "cold_load_s": round(cold, 3),
        "cold_load_includes": "Python start-up imports, catalog, parser, MiniLM index and the first page render",
        "warm_request_s": stats(warm),
        "warm_request_includes": "submitting a demo message: parse, select, validate, explain and re-render",
        "warm_selection_only_s": stats(selection),
        "target": "warm p95 < 5 s on the stated laptop (BUILD_PHASES section 6)",
        "note": "machine-dependent; not part of --check",
    }
    out = ROOT / config["outputs"]["latency"]
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: record[k] for k in ("parser", "cold_load_s", "warm_request_s", "warm_selection_only_s")},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
