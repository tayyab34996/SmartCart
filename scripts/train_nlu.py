"""Fine-tune the DistilBERT intent and slot models for every seed (Phase 6, D4).

Usage:
    python scripts/train_nlu.py                      # all seeds, both tasks
    python scripts/train_nlu.py --seeds 42 --tasks intent

Trains on the 600 training examples only; validation scores pick the epoch. Checkpoints
go to ``models/nlu/transformer/seed<seed>/<task>/`` (git-ignored) and the per-epoch
training log to ``results/metrics/nlu_training_log.json`` (tracked; figure 10 is drawn
from it). The base model must already be in the Hugging Face cache at the pinned revision.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch  # noqa: E402
import transformers  # noqa: E402

from smartcart.nlu.api import split_rows  # noqa: E402
from smartcart.nlu.training import train_task  # noqa: E402

TASKS = ("intent", "slots")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="configs/nlu_transformer.json")
    ap.add_argument("--seeds", type=int, nargs="*")
    ap.add_argument("--tasks", nargs="*", choices=TASKS)
    args = ap.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    torch.set_num_threads(config["torch_threads"])
    data = config["data"]
    train = split_rows(ROOT / data["nlu"], ROOT / data["nlu_split"], "train")
    dev = split_rows(ROOT / data["nlu"], ROOT / data["nlu_split"], "dev")
    log_path = ROOT / config["training_log"]
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"runs": {}}
    log.update({"base_model": config["base_model"], "revision": config["revision"],
                "environment": {"python": platform.python_version(), "torch": torch.__version__,
                                "transformers": transformers.__version__, "device": "cpu",
                                "torch_threads": config["torch_threads"], "machine": platform.machine()},
                "hyperparameters": {t: config[t] for t in TASKS}, "max_length": config["max_length"],
                "epoch_selection": config["epoch_selection"]})
    for seed in args.seeds or config["seeds"]:
        for task in args.tasks or TASKS:
            start = time.perf_counter()
            model, tokenizer, run = train_task(task, train, dev, config[task], seed, config["base_model"],
                                               config["revision"], config["max_length"])
            out = ROOT / config["checkpoints"].format(seed=seed, task=task)
            out.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out)
            tokenizer.save_pretrained(out)
            run["total_seconds"] = round(time.perf_counter() - start, 1)
            run["checkpoint"] = config["checkpoints"].format(seed=seed, task=task)
            log["runs"][f"seed{seed}_{task}"] = run
            print(f"seed {seed} {task}: best epoch {run['best_epoch']} dev {run['best_dev_score']} "
                  f"({run['total_seconds']} s)", flush=True)
            log["runs"] = dict(sorted(log["runs"].items()))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
