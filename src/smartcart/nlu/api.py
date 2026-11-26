"""Parser interface (BUILD_PHASES section 4.3).

``parse_request(text, catalog, parser="baseline", session=None)`` returns a
StructuredRequest. The baseline is built from ``configs/experiments/E0.json``: its intent
model is trained on the training split of ``data/annotations/nlu.jsonl`` (deterministic,
under a second) and cached per catalog. The transformer parser is added in Phase 6.
"""

from __future__ import annotations

import json
from pathlib import Path

from smartcart.nlu.baseline_parser import BaselineParser, train_intent_model
from smartcart.nlu.lexicon import Lexicon, read_recipe_aliases
from smartcart.retrieval.api import catalog_fingerprint

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "E0.json"
_PARSERS: dict[tuple[str, str], BaselineParser] = {}


def split_rows(nlu_path: Path, split_path: Path, split: str) -> list[dict]:
    """The examples of one split, checked against the split manifest."""
    manifest = json.loads(split_path.read_text(encoding="utf-8"))
    ids = set(manifest["example_ids"][split])
    rows = [json.loads(line) for line in nlu_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    chosen = [r for r in rows if r["id"] in ids]
    if len(chosen) != len(ids) or any(r["split"] != split for r in chosen):
        raise ValueError(f"{split} rows disagree with the split manifest")
    return chosen


def training_rows(nlu_path: Path, split_path: Path) -> list[dict]:
    return split_rows(nlu_path, split_path, "train")


def build_baseline_parser(catalog: dict, config: dict, root: Path = ROOT) -> BaselineParser:
    paths = config["data"]
    train = training_rows(root / paths["nlu"], root / paths["nlu_split"])
    model = train_intent_model([r["text"] for r in train], [r["intent"] for r in train], config["parser"]["intent_model"])
    lexicon = Lexicon(catalog, read_recipe_aliases(root / paths["recipe_aliases"]))
    return BaselineParser(lexicon, model, context_rules=config["parser"].get("context_rules", True))


def parse_request(text: str, catalog: dict, parser: str = "baseline", session: dict | None = None,
                  request_id: str | None = None) -> dict:
    if parser == "transformer":
        raise NotImplementedError("the transformer parser is implemented in Phase 6")
    if parser != "baseline":
        raise ValueError(f"unknown parser {parser}")
    key = (parser, catalog_fingerprint(catalog))
    if key not in _PARSERS:
        config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        _PARSERS[key] = build_baseline_parser(catalog, config)
    return _PARSERS[key].parse(text, session=session, request_id=request_id)
