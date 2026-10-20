"""Run the source audit from a checkout, without third-party dependencies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smartcart.data.audit import main


if __name__ == "__main__":
    main()
