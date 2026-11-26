"""Fine-tuning loop for the DistilBERT intent and slot models (Phase 6).

Plain PyTorch: AdamW, linear warm-up and decay, seeded shuffling. After every epoch the
model is scored on the validation split, and the epoch with the best validation score
(intent macro-F1, slot entity micro-F1; ties go to the earlier epoch) is kept. Only the
training split is used for gradient updates.
"""

from __future__ import annotations

import copy
import random
import time

import numpy as np
import torch
from torch.nn.utils.rnn import pad_sequence

from smartcart.nlu.metrics import intent_metrics, slot_metrics
from smartcart.nlu.spans import decode_bio_spans
from smartcart.nlu.transformer_parser import BIO_ID, BIO_LABELS, IGNORE, INTENT_ID, encode_words, repair_bio
from smartcart.nlu.baseline_parser import INTENTS


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _pad(batch: list[dict], pad_id: int, with_labels: str | None) -> dict:
    out = {"input_ids": pad_sequence([torch.tensor(b["input_ids"]) for b in batch], batch_first=True,
                                     padding_value=pad_id),
           "attention_mask": pad_sequence([torch.tensor(b["attention_mask"]) for b in batch], batch_first=True,
                                          padding_value=0)}
    if with_labels == "sequence":
        out["labels"] = torch.tensor([b["label"] for b in batch])
    elif with_labels == "token":
        out["labels"] = pad_sequence([torch.tensor(b["labels"]) for b in batch], batch_first=True,
                                     padding_value=IGNORE)
    return out


def intent_examples(rows: list[dict], tokenizer, max_length: int) -> list[dict]:
    out = []
    for r in rows:
        enc = tokenizer(r["text"], truncation=True, max_length=max_length)
        out.append({"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"],
                    "label": INTENT_ID[r["intent"]]})
    return out


def slot_examples(rows: list[dict], tokenizer, max_length: int) -> list[dict]:
    return [encode_words(tokenizer, r["tokens"], r["bio_tags"], max_length) for r in rows]


def _batches(n: int, batch_size: int, generator: torch.Generator | None):
    order = torch.randperm(n, generator=generator).tolist() if generator is not None else list(range(n))
    for i in range(0, n, batch_size):
        yield order[i:i + batch_size]


@torch.no_grad()
def evaluate(task: str, model, examples: list[dict], rows: list[dict], pad_id: int, batch_size: int = 64) -> dict:
    model.eval()
    losses, preds = [], []
    kind = "sequence" if task == "intent" else "token"
    for idx in _batches(len(examples), batch_size, None):
        batch = _pad([examples[i] for i in idx], pad_id, kind)
        out = model(**batch)
        losses.append(float(out.loss) * len(idx))
        logits = out.logits.argmax(-1)
        if task == "intent":
            preds.extend(logits.tolist())
        else:
            for k, i in enumerate(idx):
                tags = [BIO_LABELS[logits[k, pos].item()] for pos, first in enumerate(examples[i]["first"]) if first]
                preds.append(repair_bio(tags))
    loss = sum(losses) / len(examples)
    if task == "intent":
        scores = intent_metrics([r["intent"] for r in rows], [INTENTS[p] for p in preds], list(INTENTS))
        return {"loss": round(loss, 6), "score": scores["macro_f1"], "accuracy": scores["accuracy"]}
    gold = [decode_bio_spans(r["tokens"], r["bio_tags"]) for r in rows]
    pred = [decode_bio_spans(r["tokens"], p) for r, p in zip(rows, preds)]
    f1 = slot_metrics(gold, pred)["micro"]["f1"]
    return {"loss": round(loss, 6), "score": f1}


def train_task(task: str, train_rows: list[dict], dev_rows: list[dict], cfg: dict, seed: int, base_model: str,
               revision: str, max_length: int) -> tuple[object, object, dict]:
    """Fine-tune one model; returns (best model, tokenizer, log)."""
    from transformers import (AutoModelForSequenceClassification, AutoModelForTokenClassification, AutoTokenizer,
                              get_linear_schedule_with_warmup)
    set_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(base_model, revision=revision, local_files_only=True)
    if task == "intent":
        labels = list(INTENTS)
        model = AutoModelForSequenceClassification.from_pretrained(
            base_model, revision=revision, local_files_only=True, num_labels=len(labels),
            id2label=dict(enumerate(labels)), label2id=INTENT_ID)
        train, dev, kind = (intent_examples(train_rows, tokenizer, max_length),
                            intent_examples(dev_rows, tokenizer, max_length), "sequence")
    else:
        model = AutoModelForTokenClassification.from_pretrained(
            base_model, revision=revision, local_files_only=True, num_labels=len(BIO_LABELS),
            id2label=dict(enumerate(BIO_LABELS)), label2id=BIO_ID)
        train, dev, kind = (slot_examples(train_rows, tokenizer, max_length),
                            slot_examples(dev_rows, tokenizer, max_length), "token")
    no_decay = ("bias", "LayerNorm.weight")
    params = [{"params": [p for n, p in model.named_parameters() if not n.endswith(no_decay)],
               "weight_decay": cfg["weight_decay"]},
              {"params": [p for n, p in model.named_parameters() if n.endswith(no_decay)], "weight_decay": 0.0}]
    optimizer = torch.optim.AdamW(params, lr=cfg["learning_rate"])
    steps = cfg["epochs"] * -(-len(train) // cfg["batch_size"])
    scheduler = get_linear_schedule_with_warmup(optimizer, int(cfg["warmup_ratio"] * steps), steps)
    generator = torch.Generator().manual_seed(seed)
    pad_id = tokenizer.pad_token_id
    epochs, best, best_state = [], None, None
    for epoch in range(1, cfg["epochs"] + 1):
        model.train()
        start, total, seen = time.perf_counter(), 0.0, 0
        for idx in _batches(len(train), cfg["batch_size"], generator):
            batch = _pad([train[i] for i in idx], pad_id, kind)
            loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total += float(loss) * len(idx)
            seen += len(idx)
        dev_scores = evaluate(task, model, dev, dev_rows, pad_id)
        row = {"epoch": epoch, "train_loss": round(total / seen, 6), "dev_loss": dev_scores["loss"],
               "dev_score": dev_scores["score"], "seconds": round(time.perf_counter() - start, 2)}
        epochs.append(row)
        if best is None or row["dev_score"] > best["dev_score"]:
            best, best_state = row, copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    model.eval()
    metric = "dev_macro_f1" if task == "intent" else "dev_slot_micro_f1"
    return model, tokenizer, {"task": task, "seed": seed, "selection_metric": metric, "best_epoch": best["epoch"],
                              "best_dev_score": best["dev_score"], "epochs": epochs,
                              "train_examples": len(train), "dev_examples": len(dev)}
