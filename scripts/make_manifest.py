"""Write the run manifest: what the reported results were produced from (Phase 12, D10).

Usage:
    python scripts/make_manifest.py            # write results/run_manifest.json
    python scripts/make_manifest.py --check    # rebuild in memory and compare; also check the environment

The manifest records, for the committed results:
- the seeds used anywhere in the pipeline (read from the frozen configs);
- the pinned package versions (from ``requirements-lock.txt``) and the lock file's hash;
- the two Hugging Face base models with their revisions, and the SHA-256 of the six
  fine-tuned DistilBERT checkpoint weights (``models/`` is not on GitHub);
- the two source archives (bytes and SHA-256, from ``docs/data_audit.md``);
- the SHA-256 of every committed input (catalog, recipes, mappings, annotations,
  benchmarks, splits, rules, configs), and of the Phase 11 tables and metrics.

Text files are hashed as UTF-8 text with line endings normalised, so a Windows (CRLF)
checkout gives the same hashes. Machine-dependent latency files are left out.

``--check`` fails if the rebuilt manifest differs, if an installed package version
differs from the lock file, if a checkpoint is missing, or if a raw archive that is
present has a different hash. Missing raw archives are reported, not failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = "results/run_manifest.json"

INPUT_GLOBS = [
    "data/processed/catalog.json", "data/processed/*.csv",
    "data/annotations/*.jsonl", "data/benchmarks/*.json", "data/splits/*.json",
    "configs/*.json", "configs/*.csv", "configs/experiments/*.json",
]
RESULT_GLOBS = [
    "results/tables/*.md", "results/metrics/phase11_summary.json",
    "results/metrics/test_components.json", "results/metrics/runs/*.json",
]
MACHINE_DEPENDENT = re.compile(r"(latency)")
# Inherited EDA files (before the phase plan); no reported result reads them.
NOT_RESULT_INPUTS = {"data/processed/cleaned_instacart_data.csv", "data/processed/scaled_features.csv"}
KEY_PACKAGES = ["torch", "transformers", "sentence-transformers", "faiss-cpu", "scikit-learn",
                "ortools", "mlxtend", "streamlit", "numpy", "pandas", "pytest"]


def json_text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def config(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def lock_versions() -> dict[str, str]:
    out = {}
    for line in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "==" in line:
            name, version = line.split(";")[0].split("==", 1)
            out[canonical(name)] = version.strip()
    return out


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower().strip()


def hashed(globs: list[str]) -> dict[str, str]:
    paths = sorted({p for g in globs for p in ROOT.glob(g) if p.is_file()})
    return {p.relative_to(ROOT).as_posix(): text_sha256(p) for p in paths
            if not MACHINE_DEPENDENT.search(p.name) and p.relative_to(ROOT).as_posix() not in NOT_RESULT_INPUTS}


def sources() -> dict:
    audit = (ROOT / "docs/data_audit.md").read_text(encoding="utf-8")
    rows = re.findall(r"\| `(data/raw/[^`]+)` \| ([\d,]+) \| `([0-9a-f]{64})` \|", audit)
    names = {"archive_3.zip": "Instacart Market Basket Analysis (Kaggle)",
             "archive_4.zip": "Food.com Recipes and Reviews, irkaal (Kaggle)"}
    return {path: {"dataset": names.get(Path(path).name, ""), "bytes": int(size.replace(",", "")),
                   "sha256": digest} for path, size, digest in rows}


def checkpoints(nlu: dict) -> dict[str, str | None]:
    out = {}
    for seed in nlu["seeds"]:
        for task in ("intent", "slots"):
            path = ROOT / nlu["checkpoints"].format(seed=seed, task=task) / "model.safetensors"
            out[f"seed{seed}/{task}"] = file_sha256(path) if path.exists() else None
    return out


def build(with_checkpoints: bool = True) -> dict:
    nlu = config("configs/nlu_transformer.json")
    retrieval = config("configs/retrieval.json")
    solver = config("configs/solver.json")
    associations = config("configs/associations.json")
    evaluation = config("configs/experiments/evaluation.json")
    e0 = config("configs/experiments/E0.json")
    locked = re.findall(r"\| `([^`]+)` \| `([0-9a-f]{64})` \| locked \|",
                        (ROOT / "docs/benchmark_lock.md").read_text(encoding="utf-8"))
    versions = lock_versions()
    return {
        "description": "What the committed results were produced from. Rebuild with "
                       "scripts/make_manifest.py; verify with --check.",
        "python": "3.11 (requirements-lock.txt was tested with 3.11.9 on Windows)",
        "environment": {
            "lock_file": "requirements-lock.txt",
            "lock_file_sha256": text_sha256(ROOT / "requirements-lock.txt"),
            "pinned_packages": len(versions),
            "key_packages": {p: versions.get(p) for p in KEY_PACKAGES},
            "torch_build": "CPU wheels from https://download.pytorch.org/whl/cpu",
        },
        "models": {
            "distilbert_base": {"name": nlu["base_model"], "revision": nlu["revision"]},
            "minilm": {"name": retrieval["model"]["name"], "revision": retrieval["model"]["revision"]},
            "distilbert_checkpoints": {
                "path": nlu["checkpoints"] + "/model.safetensors (not on GitHub)",
                "sha256": checkpoints(nlu) if with_checkpoints else None,
            },
        },
        "seeds": {
            "benchmarks_and_annotations": config("configs/benchmarks.json")["seed"],
            "instacart_sample": config("configs/instacart_sample.json")["seed"],
            "distilbert_training": nlu["seeds"],
            "distilbert_primary": nlu["primary_seed"],
            "e0_linear_svc_random_state": e0["parser"]["intent_model"]["classifier"]["random_state"],
            "cp_sat_random_seed": solver_seed(solver),
            "track_b_user_split": associations["trackb"]["user_split"]["seed"],
            "phase11_transformer_seeds": evaluation["seeds"],
            "phase11_bootstrap": evaluation["bootstrap"]["seed"],
        },
        "sources": sources(),
        "locked_test_files": {path: digest for path, digest in locked},
        "inputs": hashed(INPUT_GLOBS),
        "results": hashed(RESULT_GLOBS),
    }


def solver_seed(solver: dict):
    found = find_key(solver, "random_seed")
    return found[0] if found else None


def find_key(obj, key: str) -> list:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out.extend(find_key(v, key))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(find_key(v, key))
    return out


def environment_problems() -> list[str]:
    problems = []
    for name, version in lock_versions().items():
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            problems.append(f"{name}: not installed (lock {version})")
            continue
        if installed != version:
            problems.append(f"{name}: installed {installed}, lock {version}")
    return problems


def raw_archive_problems(srcs: dict) -> tuple[list[str], list[str]]:
    problems, notes = [], []
    for path, info in srcs.items():
        p = ROOT / path
        if not p.exists():
            notes.append(f"{path}: absent (not checked)")
        elif file_sha256(p) != info["sha256"]:
            problems.append(f"{path}: SHA-256 differs from docs/data_audit.md")
        else:
            notes.append(f"{path}: ok")
    return problems, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    manifest = build()
    missing = [k for k, v in manifest["models"]["distilbert_checkpoints"]["sha256"].items() if v is None]
    if missing:
        print("DistilBERT checkpoints missing: " + ", ".join(missing))
        return 1
    if not args.check:
        (ROOT / OUT).write_text(json_text(manifest), encoding="utf-8", newline="\n")
        print(f"wrote {OUT}: {len(manifest['inputs'])} inputs, {len(manifest['results'])} results")
        return 0
    committed = json.loads((ROOT / OUT).read_text(encoding="utf-8")) if (ROOT / OUT).exists() else {}
    bad = sorted(k for k in set(manifest) | set(committed) if manifest.get(k) != committed.get(k))
    for k in manifest:
        print(("DIFFERS " if k in bad else "same    ") + k)
    if "inputs" in bad or "results" in bad:
        for section in ("inputs", "results"):
            a, b = manifest[section], committed.get(section, {})
            for path in sorted(set(a) | set(b)):
                if a.get(path) != b.get(path):
                    print(f"  {section}: {path}")
    env = environment_problems()
    for line in env:
        print("ENV " + line)
    print(f"environment: {'matches' if not env else 'DIFFERS from'} requirements-lock.txt")
    raw_bad, notes = raw_archive_problems(manifest["sources"])
    for line in notes + raw_bad:
        print("raw " + line)
    return 1 if bad or env or raw_bad else 0


if __name__ == "__main__":
    sys.exit(main())
