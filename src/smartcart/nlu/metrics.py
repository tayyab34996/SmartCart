"""NLU metrics shared by the baseline (Phase 5) and the transformer parser (Phase 6).

- Intent: accuracy, macro-F1, per-class precision/recall/F1/support, confusion matrix.
- Slots: entity-level micro precision/recall/F1 over exact (label, start, end) character
  spans, overall and per label.
- Quantity attachment: share of gold QUANTITY and UNIT spans that are predicted exactly
  and attached to the exactly predicted gold item.
- Request fields: exact budget and servings (over examples whose gold field is set, plus
  spurious values where it is not), clarification decisions and types, and whole-request
  exact match (ignoring ``request_id``, ``user_id`` and the prompt wording).
"""

from __future__ import annotations

from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

SLOT_LABELS = ("MEAL", "PRODUCT", "BUDGET", "CURRENCY", "SERVINGS", "QUANTITY", "UNIT", "DIET", "EXCLUSION", "PANTRY")
REQUEST_IGNORED = {"request_id", "user_id", "clarification_prompt"}


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 6) if den else None


def intent_metrics(gold: list[str], pred: list[str], labels: list[str]) -> dict:
    p, r, f, s = precision_recall_fscore_support(gold, pred, labels=labels, zero_division=0)
    return {
        "accuracy": _rate(sum(g == q for g, q in zip(gold, pred)), len(gold)),
        "macro_f1": round(float(f1_score(gold, pred, labels=labels, average="macro", zero_division=0)), 6),
        "per_class": {lab: {"precision": round(float(p[i]), 6), "recall": round(float(r[i]), 6),
                            "f1": round(float(f[i]), 6), "support": int(s[i])} for i, lab in enumerate(labels)},
        "labels": labels,
        "confusion_matrix": confusion_matrix(gold, pred, labels=labels).tolist(),
    }


def _key(span: dict) -> tuple:
    return span["label"], span["start"], span["end"]


def slot_metrics(gold_spans: list[list[dict]], pred_spans: list[list[dict]]) -> dict:
    counts = {lab: [0, 0, 0] for lab in SLOT_LABELS}  # tp, fp, fn
    for gold, pred in zip(gold_spans, pred_spans):
        g, q = {_key(s) for s in gold}, {_key(s) for s in pred}
        for k in g & q:
            counts[k[0]][0] += 1
        for k in q - g:
            counts.setdefault(k[0], [0, 0, 0])[1] += 1
        for k in g - q:
            counts.setdefault(k[0], [0, 0, 0])[2] += 1

    def prf(tp: int, fp: int, fn: int) -> dict:
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return {"precision": round(prec, 6), "recall": round(rec, 6), "f1": round(f1, 6), "tp": tp, "fp": fp, "fn": fn}

    total = [sum(c[i] for c in counts.values()) for i in range(3)]
    return {"micro": prf(*total), "per_label": {lab: prf(*c) for lab, c in counts.items()}}


def attachment_accuracy(gold_spans: list[list[dict]], pred_spans: list[list[dict]]) -> dict:
    correct = total = 0
    for gold, pred in zip(gold_spans, pred_spans):
        pred_index = {_key(s): s for s in pred}
        for span in gold:
            if span["label"] not in {"QUANTITY", "UNIT"} or span["attach_to"] is None:
                continue
            total += 1
            match = pred_index.get(_key(span))
            if match is not None and match["attach_to"] is not None \
                    and _key(pred[match["attach_to"]]) == _key(gold[span["attach_to"]]):
                correct += 1
    return {"accuracy": _rate(correct, total), "correct": correct, "total": total}


def field_metrics(gold: list[dict], pred: list[dict], field: str) -> dict:
    set_pairs = [(g[field], p[field]) for g, p in zip(gold, pred) if g[field] is not None]
    unset_pairs = [(g[field], p[field]) for g, p in zip(gold, pred) if g[field] is None]
    correct = sum(g == p for g, p in set_pairs)
    spurious = sum(p is not None for _, p in unset_pairs)
    return {"exact_accuracy": _rate(correct, len(set_pairs)), "correct": correct, "gold_set": len(set_pairs),
            "spurious_when_gold_unset": spurious, "gold_unset": len(unset_pairs)}


def clarification_metrics(gold: list[dict], pred: list[dict]) -> dict:
    asked_gold = [g["needs_clarification"] for g in gold]
    asked_pred = [p["needs_clarification"] for p in pred]
    tp = sum(a and b for a, b in zip(asked_gold, asked_pred))
    type_ok = sum(g["clarification_type"] == p["clarification_type"]
                  for g, p in zip(gold, pred) if g["needs_clarification"])
    return {"gold_clarifications": sum(asked_gold), "predicted_clarifications": sum(asked_pred),
            "recall": _rate(tp, sum(asked_gold)), "precision": _rate(tp, sum(asked_pred)),
            "type_accuracy": _rate(type_ok, sum(asked_gold)),
            "unnecessary": sum(b and not a for a, b in zip(asked_gold, asked_pred))}


def comparable_request(request: dict) -> dict:
    return {k: v for k, v in request.items() if k not in REQUEST_IGNORED}


def request_exact_match(gold: list[dict], pred: list[dict]) -> dict:
    correct = sum(comparable_request(g) == comparable_request(p) for g, p in zip(gold, pred))
    return {"accuracy": _rate(correct, len(gold)), "correct": correct, "total": len(gold)}
