"""Run every Phase 11 evaluation in order (D9).

Usage:
    python scripts/evaluate_all.py            # the test split: lock check, components, 9 runs, report
    python scripts/evaluate_all.py --check    # rebuild everything in memory and compare

Each step is a separate process, so every run's cold load is measured from a fresh
start. The locked files are verified first; nothing runs if they changed. Stops at the
first failing step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.pipeline.experiment import verify_lock  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evaluation", default="configs/experiments/evaluation.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    evaluation = json.loads((ROOT / args.evaluation).read_text(encoding="utf-8"))
    lock = verify_lock(ROOT, ROOT / evaluation["lock"])
    for path, ok in lock.items():
        print(("lock ok   " if ok else "LOCK FAIL ") + path)
    if not all(lock.values()):
        return 1
    extra = ["--check"] if args.check else []
    steps = [["scripts/evaluate_components.py", *extra]]
    steps += [["scripts/evaluate.py", "--config", f"configs/experiments/{run}.json", *extra]
              for run in evaluation["runs"]]
    steps.append(["scripts/make_report.py", *extra])
    for step in steps:
        start = time.perf_counter()
        print(f"\n=== {' '.join(step)} ===", flush=True)
        code = subprocess.run([sys.executable, *step], cwd=ROOT).returncode
        print(f"=== exit {code} after {time.perf_counter() - start:.0f} s ===", flush=True)
        if code != 0:
            return code
    print("\nall Phase 11 steps finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
