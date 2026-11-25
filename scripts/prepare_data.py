"""Build data/processed/catalog.json and write catalog checks (Phase 2, D2).

Usage:  .venv\\Scripts\\python scripts\\prepare_data.py [--config configs/catalog_build.json] [--check]

--check rebuilds in memory and fails if the committed catalog differs (reproducibility check).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.data.catalog_build import build_catalog, read_csv  # noqa: E402
from smartcart.data.catalog_checks import run_catalog_checks  # noqa: E402


def dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/catalog_build.json"))
    parser.add_argument("--check", action="store_true", help="verify the committed catalog is reproducible")
    args = parser.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    catalog = build_catalog(ROOT, config)
    output = ROOT / config["output"]
    if args.check:
        same = output.is_file() and output.read_text(encoding="utf-8") == dump(catalog)
        print("catalog reproducible:", same)
        return 0 if same else 1
    line_rows = read_csv(ROOT / config["inputs"]["recipe_lines"])
    checks = run_catalog_checks(catalog, config["targets"], line_rows)
    output.write_text(dump(catalog), encoding="utf-8")
    checks_path = ROOT / config["checks_output"]
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_text(dump(checks), encoding="utf-8")
    print(json.dumps({"counts": checks["counts"], "checks": checks["checks"]}, indent=2))
    return 0 if checks["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
