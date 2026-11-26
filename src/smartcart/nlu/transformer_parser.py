"""Phase 6 (D4): DistilBERT intent and slot models wrapped as a StructuredRequest parser.

Two fine-tuned ``distilbert-base-uncased`` models:

- **intent**: sequence classification over the 4 intents;
- **slots**: token classification over BIO tags for the 10 slot labels. Words are the
  project tokenizer's tokens (``benchmarks.language.tokenize``); only the first sub-token
  of each word carries a label, the rest are ignored (-100) in training and in decoding.

``TransformerParser`` reuses everything after tagging from the E0 parser (value
normalisation through ``SpanNormalizer``, revision merging, the clarification rules and
answer handling), and adds:

- temperature-scaled intent confidence (temperature fitted on validation data);
- a ``low_confidence_intent`` question when the calibrated confidence is below a
  threshold chosen on validation data (runtime only; never a gold label);
- up to three supported, feasible recipe suggestions when the dish is missing.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from smartcart.benchmarks.language import tokenize  # noqa: E402
from smartcart.nlu.baseline_parser import INTENTS, BaselineParser  # noqa: E402
from smartcart.nlu.metrics import SLOT_LABELS  # noqa: E402
from smartcart.nlu.normalize import SpanNormalizer  # noqa: E402

BIO_LABELS = ["O"] + [f"{p}-{label}" for label in SLOT_LABELS for p in ("B", "I")]
BIO_ID = {tag: i for i, tag in enumerate(BIO_LABELS)}
INTENT_ID = {intent: i for i, intent in enumerate(INTENTS)}
IGNORE = -100
LOW_CONFIDENCE_PROMPT = ("I'm not sure what you'd like. Do you want to plan a meal, build a grocery list, "
                         "change your current basket, or something else?")


# ---------------------------------------------------------------- encoding
def encode_words(tokenizer, words: list[str], tags: list[str] | None, max_length: int) -> dict:
    """Sub-word encoding of pre-split words; labels on the first sub-token of each word only."""
    enc = tokenizer(words, is_split_into_words=True, truncation=True, max_length=max_length)
    word_ids = enc.word_ids()
    if any(w is not None for w in word_ids) and max(w for w in word_ids if w is not None) < len(words) - 1:
        raise ValueError(f"input longer than max_length={max_length}: {' '.join(words)}")
    first = []
    labels = []
    previous = None
    for w in word_ids:
        is_first = w is not None and w != previous
        first.append(is_first)
        labels.append(BIO_ID[tags[w]] if (is_first and tags is not None) else IGNORE)
        previous = w
    out = {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"], "first": first,
           "word_ids": word_ids}
    if tags is not None:
        out["labels"] = labels
    return out


def repair_bio(tags: list[str]) -> list[str]:
    """An I- tag that does not continue a span of the same label starts a new span."""
    out = []
    for i, tag in enumerate(tags):
        if tag.startswith("I-") and (i == 0 or out[-1][2:] != tag[2:]):
            tag = "B-" + tag[2:]
        out.append(tag)
    return out


def tags_to_spans(text: str, tags: list[str]) -> list[dict]:
    """Character spans (label, start, end, text) from word-level BIO tags over ``tokenize(text)``."""
    tokens = tokenize(text)
    spans, current = [], None
    for (_, start, end), tag in zip(tokens, repair_bio(tags)):
        if tag.startswith("B-"):
            if current:
                spans.append(current)
            current = {"label": tag[2:], "start": start, "end": end}
        elif tag.startswith("I-") and current:
            current["end"] = end
        else:
            if current:
                spans.append(current)
            current = None
    if current:
        spans.append(current)
    return [{**s, "text": text[s["start"]:s["end"]]} for s in spans]


# ---------------------------------------------------------------- calibration
def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = logits / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll(logits: np.ndarray, labels: np.ndarray, temperature: float) -> float:
    p = softmax(logits, temperature)[np.arange(len(labels)), labels]
    return float(-np.log(np.clip(p, 1e-12, 1.0)).mean())


def fit_temperature(logits: np.ndarray, labels: np.ndarray, grid: list[float]) -> float:
    """Temperature with the lowest validation NLL; ties go to the value closest to 1."""
    scored = [(round(nll(logits, labels, t), 9), abs(math.log(t)), t) for t in grid]
    return min(scored)[2]


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
    conf = probs.max(axis=1)
    correct = probs.argmax(axis=1) == labels
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        mask = (conf > lo) & (conf <= hi) if b else (conf >= lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return round(float(ece), 6)


def choose_threshold(confidence: list[float], correct: list[bool], grid: list[float]) -> dict:
    """Threshold maximising (wrong intents caught - correct intents questioned); ties go lower."""
    rows = []
    for t in grid:
        flagged = [c < t for c in confidence]
        caught = sum(f and not ok for f, ok in zip(flagged, correct))
        needless = sum(f and ok for f, ok in zip(flagged, correct))
        rows.append({"threshold": t, "wrong_caught": caught, "correct_questioned": needless,
                     "net": caught - needless})
    best = max(rows, key=lambda r: (r["net"], -r["threshold"]))
    return {"threshold": best["threshold"], "grid": rows}


# ---------------------------------------------------------------- models
class IntentModel:
    def __init__(self, path: Path, max_length: int):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True).eval()
        self.max_length = max_length
        self.classes = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]

    @torch.no_grad()
    def logits(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tokenizer(texts[i:i + batch_size], padding=True, truncation=True, max_length=self.max_length,
                                 return_tensors="pt")
            out.append(self.model(**enc).logits.numpy())
        return np.concatenate(out) if out else np.zeros((0, len(self.classes)))


class SlotModel:
    def __init__(self, path: Path, max_length: int):
        from transformers import AutoModelForTokenClassification, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForTokenClassification.from_pretrained(path, local_files_only=True).eval()
        self.max_length = max_length
        self.labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]

    @torch.no_grad()
    def tag_words(self, words: list[str]) -> list[str]:
        if not words:
            return []
        enc = encode_words(self.tokenizer, words, None, self.max_length)
        ids = torch.tensor([enc["input_ids"]])
        mask = torch.tensor([enc["attention_mask"]])
        pred = self.model(input_ids=ids, attention_mask=mask).logits[0].argmax(-1).tolist()
        tags = ["O"] * len(words)
        for pos, (w, is_first) in enumerate(zip(enc["word_ids"], enc["first"])):
            if is_first:
                tags[w] = self.labels[pred[pos]]
        return tags

    def tag(self, text: str) -> list[str]:
        return self.tag_words([t for t, _, _ in tokenize(text)])


class TransformerParser(BaselineParser):
    """parse(text, session) with DistilBERT intent and slots; shared normalisation and rules."""

    def __init__(self, lexicon, intent_model: IntentModel, slot_model: SlotModel, temperature: float = 1.0,
                 threshold: float = 0.0, context_rules: bool = True, suggest_recipes: bool = True):
        super().__init__(lexicon, intent_model, context_rules=context_rules, suggest_recipes=suggest_recipes)
        self.slot_model = slot_model
        self.normalizer = SpanNormalizer(lexicon)
        self.temperature = temperature
        self.threshold = threshold
        self._span_cache: dict[str, list[dict]] = {}

    def predict_intent(self, text: str) -> tuple[str, dict]:
        probs = softmax(self.intent_model.logits([text]), self.temperature)[0]
        classes = self.intent_model.classes
        return classes[int(probs.argmax())], {c: round(float(p), 6) for c, p in zip(classes, probs)}

    def extract_spans(self, text: str, intent: str) -> list[dict]:
        if intent == "unsupported":
            return []
        if text not in self._span_cache:
            raw = tags_to_spans(text, self.slot_model.tag(text))
            self._span_cache[text] = self.normalizer.normalise(raw)
        return [dict(s) for s in self._span_cache[text]]

    def confidence_gate(self, request: dict, scores: dict, classifier_decided: bool) -> dict:
        if classifier_decided and max(scores.values()) < self.threshold:
            request = dict(request)
            request.update(needs_clarification=True, clarification_type="low_confidence_intent",
                           clarification_prompt=LOW_CONFIDENCE_PROMPT)
        return request
