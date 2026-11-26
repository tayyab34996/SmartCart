# Setting up SmartCart to continue from Phase 7

Phases 0–6 are complete, committed and pushed. This guide gets a fresh clone to the same
state, so work on Phase 7 onwards builds on identical data, models and results.

The steps below are meant for Claude Code to carry out on the teammate's machine. All
commands are for **PowerShell, run from the repository root**. Run the steps in order.

## Before you start: files the teammate adds by hand

These are not on GitHub. The teammate places them before setup begins:

| File or folder | Contents |
| --- | --- |
| `data\raw\archive_3.zip` | Instacart Market Basket Analysis (Kaggle) |
| `data\raw\archive_4.zip` | Food.com Recipes and Reviews by irkaal (Kaggle) |
| `models\nlu\transformer\` | Fine-tuned DistilBERT checkpoints (about 1.5 GB, shared by the owner) |

Step 1 checks that they are in the right place and are the correct versions.

## 1. Check the hand-added files

**Raw data hashes:**

```powershell
Get-FileHash data\raw\archive_3.zip -Algorithm SHA256
Get-FileHash data\raw\archive_4.zip -Algorithm SHA256
```

They must match `docs/data_audit.md`:

- `archive_3.zip`: `c347cd7fa301c068ed391c7c77620f0e26e18f65d04cb907b6389c670db03038`
- `archive_4.zip`: `fa7910c9591997641448147809faa21b4bba539c01225fda2ab6b315b5f7527d`

If a file is missing, misnamed or has a different hash, stop and tell the teammate. A
different dataset version means the results will not reproduce.

**Checkpoint layout.** All 6 of these must exist:

```powershell
foreach ($s in 13, 42, 7) { foreach ($t in "intent", "slots") {
  "$s $t " + (Test-Path "models\nlu\transformer\seed$s\$t\model.safetensors") } }
```

Every line must end in `True`. Each folder holds `config.json`, `model.safetensors`,
`tokenizer.json` and `tokenizer_config.json`. If the zip unpacked with an extra folder level
(for example `models\nlu\transformer\transformer\seed13`), move the seed folders up one
level.

**Do not retrain these models.** Retrained models would differ slightly from the ones behind
the committed Phase 6 results, so those results would stop matching.

## 2. Python environment

The project needs **Python 3.11** (`py -3.11 --version`). The repository should sit at a
short path such as `D:\SmartCart`; Windows' 260-character path limit breaks the PyTorch
install in deep folders.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

`requirements-lock.txt` pins every package version, and the extra index supplies the
CPU-only PyTorch build. From here on, run project code with `.\.venv\Scripts\python`.
Everything runs on the CPU.

## 3. Hugging Face models

Download the two base models into the local Hugging Face cache:

```powershell
$env:HF_HUB_DISABLE_XET = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
.\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('sentence-transformers/all-MiniLM-L6-v2')"
.\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('distilbert/distilbert-base-uncased', revision='12040accade4e8a0f71eabdb258fecc2e7e948be', allow_patterns=['config.json','tokenizer.json','tokenizer_config.json','vocab.txt','model.safetensors'])"
```

- `HF_HUB_DISABLE_XET=1` avoids a "404 xet-read-token" error in the newer download backend.
- The symlinks warning on Windows is harmless.
- No Hugging Face account or token is needed.
- **MiniLM** (`all-MiniLM-L6-v2`) is the Phase 7 semantic retriever.
- The **DistilBERT base**, pinned to the revision the project used, is needed by the
  tokenizer tests and by any future retraining.
- The code loads both with `local_files_only=True`, and the scripts set
  `HF_HUB_OFFLINE=1`. After this step, nothing needs the internet.

## 4. Rebuild the Instacart working files

`data\interim\` is not on GitHub: it contains Instacart product names and basket rows.
Phase 8 and the benchmark rebuild check need it.

```powershell
.\.venv\Scripts\python scripts/prepare_transactions.py
```

This takes about 20 seconds and writes `data\interim\instacart\`.

## 5. Check that everything reproduces

Run these before changing anything:

```powershell
.\.venv\Scripts\python scripts/prepare_data.py --check
.\.venv\Scripts\python scripts/prepare_transactions.py --check
.\.venv\Scripts\python scripts/build_benchmarks.py --check
.\.venv\Scripts\python scripts/run_baseline.py --check
.\.venv\Scripts\python scripts/evaluate_nlu.py --check
.\.venv\Scripts\python -m pytest
```

Expected results:

- Every `--check` prints only `same` lines and exits without an error.
- `pytest` reports **164 passed, 95 subtests passed** in about 2 minutes.
- If 3 tests are skipped, the checkpoints are missing or misplaced (go back to step 1).

If anything differs, do not start Phase 7. Find the setup difference first and report it
to the teammate.

Optional, but it reproduces the raw-data audit report (`docs/data_audit.md`), which takes
about 4 minutes:

```powershell
.\.venv\Scripts\python scripts/audit_data.py --config configs/data_audit.json
```

## 6. Read before starting

1. `CLAUDE.md`: working rules (Claude Code reads it automatically).
2. `docs/BUILD_PHASES.md`: the plan. Read sections 1–4 once, then the phase you are on.
3. `docs/progress.md`: what is done, what was found, and the **"Next task"** section at
   the bottom, which describes Phase 7.
4. `docs/benchmark_policy.md`: what the benchmark labels mean.
5. `docs/benchmark_lock.md`: the locked test files.
6. `docs/nlu_failures.md`: Phase 6 findings and an open decision.

## 7. Working together on GitHub

- Commit messages are short and imperative ("Add MiniLM index builder"). Make one commit
  per feature, and **do not add AI co-author lines**.
- Never commit `models/`, `data/raw/` or `data/interim/`. `.gitignore` already blocks them.

## Open items inherited from Phases 0–6

| Item | Where | Status |
| --- | --- | --- |
| Fix the diet check (`is True` must be `== "allowed"`) | `src/smartcart/retrieval/filtering.py` | Part of Phase 7 |
| Product text for both retrievers (TF-IDF currently includes the ingredient name) | Phase 7 | To decide in Phase 7 |
| NLU test-set metrics for both parsers | Phase 11 | Deferred on purpose: one look at test data |
| Optional parser variants (hybrid; snapping spans to the catalog) | `docs/nlu_failures.md` | Owner's decision before Phase 11 |
| Second-person review of 180 annotations | `docs/annotation_review.md` | Pending; needs a teammate |
| Independent review of the 42 recipes, and of the 300 Instacart mapping rows | `docs/progress.md` (Phases 2–3) | Pending |
| Team literature-matrix spreadsheet | `docs/literature/` | Pending |
