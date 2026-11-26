"""Parser interface (BUILD_PHASES section 4.3).

``parse_request(text, catalog, parser="baseline", session=None)`` returns a
StructuredRequest. The baseline is built from ``configs/experiments/E0.json``: its intent
model is trained on the training split of ``data/annotations/nlu.jsonl`` (deterministic,
under a second) and cached per catalog.

The transformer parser (Phase 6) loads fine-tuned checkpoints from
``configs/nlu_transformer.json`` (``models/nlu/transformer/seed<seed>/``, created by
``scripts/train_nlu.py``) with the per-seed calibration frozen in that config. ``seed``
defaults to the config's primary seed; Phase 11 runs all three.
"""

from __future__ import annotations

import json
from pathlib import Path

from smartcart.nlu.baseline_parser import BaselineParser, train_intent_model
from smartcart.nlu.lexicon import Lexicon, read_recipe_aliases
from smartcart.retrieval.api import catalog_fingerprint

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "E0.json"
TRANSFORMER_CONFIG = ROOT / "configs" / "nlu_transformer.json"
_PARSERS: dict[tuple, BaselineParser] = {}


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


def load_transformer_parser(catalog: dict, config: dict, seed: int, root: Path = ROOT, calibrated: bool = True):
    from smartcart.nlu.transformer_parser import IntentModel, SlotModel, TransformerParser
    paths = {task: root / config["checkpoints"].format(seed=seed, task=task) for task in ("intent", "slots")}
    missing = [str(p) for p in paths.values() if not (p / "config.json").exists()]
    if missing:
        raise FileNotFoundError(f"missing checkpoints {missing}; run scripts/train_nlu.py first")
    calibration = config.get("calibration", {}).get(str(seed)) if calibrated else None
    if calibrated and calibration is None:
        raise ValueError(f"no frozen calibration for seed {seed}; run scripts/evaluate_nlu.py --calibrate")
    lexicon = Lexicon(catalog, read_recipe_aliases(root / config["data"]["recipe_aliases"]))
    return TransformerParser(lexicon, IntentModel(paths["intent"], config["max_length"]),
                             SlotModel(paths["slots"], config["max_length"]),
                             temperature=calibration["temperature"] if calibration else 1.0,
                             threshold=calibration["threshold"] if calibration else 0.0,
                             context_rules=config.get("context_rules", True),
                             suggest_recipes=config.get("suggest_recipes", True))


def parse_request(text: str, catalog: dict, parser: str = "baseline", session: dict | None = None,
                  request_id: str | None = None, seed: int | None = None) -> dict:
    if parser not in {"baseline", "transformer"}:
        raise ValueError(f"unknown parser {parser}")
    if parser == "transformer":
        config = json.loads(TRANSFORMER_CONFIG.read_text(encoding="utf-8"))
        seed = config["primary_seed"] if seed is None else seed
        key = (parser, seed, catalog_fingerprint(catalog))
        if key not in _PARSERS:
            _PARSERS[key] = load_transformer_parser(catalog, config, seed)
    else:
        key = (parser, catalog_fingerprint(catalog))
        if key not in _PARSERS:
            config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
            _PARSERS[key] = build_baseline_parser(catalog, config)
    return _PARSERS[key].parse(text, session=session, request_id=request_id)
