"""Validate the curated pilot records and optionally display scaled requirements."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.data.contracts import ContractError, load_pilot, requirements_for, validate_pilot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/processed/pilot/catalog.json")
    parser.add_argument("--recipe")
    parser.add_argument("--servings", type=int)
    args = parser.parse_args()
    if (args.recipe is None) != (args.servings is None):
        parser.error("--recipe and --servings must be supplied together")
    try:
        data = load_pilot(args.data)
        result = validate_pilot(data)
        if args.recipe is not None:
            result["requirements"] = requirements_for(data, args.recipe, args.servings)
    except (ContractError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
