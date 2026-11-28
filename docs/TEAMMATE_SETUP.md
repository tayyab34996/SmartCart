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
.\.venv\Scripts\python scripts/build_index.py
.\.venv\Scripts\python scripts/build_index.py --check
.\.venv\Scripts\python scripts/evaluate_retrieval.py --check
.\.venv\Scripts\python scripts/mine_rules.py --check
.\.venv\Scripts\python scripts/evaluate_trackb.py --check
.\.venv\Scripts\python scripts/run_solver.py --check
.\.venv\Scripts\python scripts/run_demo_cases.py --check
.\.venv\Scripts\python scripts/evaluate_all.py --check
.\.venv\Scripts\python scripts/make_manifest.py --check
.\.venv\Scripts\python -m pytest
```

Expected results:

- Every `--check` prints only `same` lines and exits without an error.
- `build_index.py` (without `--check`) builds the git-ignored MiniLM index cache in
  `models\retrieval\` (Phase 7); retrieval also works without it, only slower to start.
- `evaluate_all.py --check` (Phase 11) first prints `lock ok` for the five locked test
  files, then rebuilds every Phase 11 result in memory and compares it with the committed
  files. It takes about 30 minutes; it reads the test sets with the frozen configs and
  changes nothing.
- `make_manifest.py --check` (Phase 12) also confirms that the installed packages match
  `requirements-lock.txt` and that the raw archives and checkpoints have the recorded
  hashes.
- `pytest` reports **259 passed** in about 12 minutes (Phase 12). pytest 9 hides the
  passed-subtest count at the default verbosity; with `-q` or `-v` the summary also shows
  **95 subtests passed**.
- If 3 tests are skipped, the checkpoints are missing or misplaced (go back to step 1).

If anything differs, do not start the next phase. Find the setup difference first and report it
to the teammate.

To open the interface (Phase 10): `.\.venv\Scripts\python -m streamlit run website/app.py`. The first
load takes about half a minute while the models load.

Optional, but it reproduces the raw-data audit report (`docs/data_audit.md`), which takes
about 4 minutes:

```powershell
.\.venv\Scripts\python scripts/audit_data.py --config configs/data_audit.json
```

## 6. Read before starting

1. `CLAUDE.md`: working rules (Claude Code reads it automatically).
2. `docs/BUILD_PHASES.md`: the plan. Read sections 1–4 once, then the phase you are on.
3. `docs/progress.md`: what is done, what was found, and the **"Next task"** section at
   the bottom, which describes the next phase.
4. `docs/benchmark_policy.md`: what the benchmark labels mean.
5. `docs/benchmark_lock.md`: the locked test files.
6. `docs/nlu_failures.md`: Phase 6 findings and the decision taken before Phase 11.
7. `docs/failure_analysis.md`: what fails on the test split, and why (Phase 11).

## 7. Working together on GitHub

- Commit messages are short and imperative ("Add MiniLM index builder"). Make one commit
  per feature, and **do not add AI co-author lines**.
- Never commit `models/`, `data/raw/` or `data/interim/`. `.gitignore` already blocks them.

## Open items inherited from Phases 0–6

| Item | Where | Status |
| --- | --- | --- |
| Fix the diet check (`is True` must be `== "allowed"`) | `src/smartcart/retrieval/filtering.py` | Done in Phase 7 |
| Product text for both retrievers | `configs/retrieval.json` | Decided in Phase 7 (`display_name_ingredient`); E0 keeps the Phase 1 text (Phase 11 ran E0 as frozen) |
| NLU, retrieval and Track B test-set metrics | `results/metrics/test_components.json` | Done in Phase 11 (one test run, frozen configs) |
| Optional parser variants (hybrid; snapping spans to the catalog) | `docs/nlu_failures.md` | Decided 2026-11-28: not added; Phase 11 runs E0–E4 and A1–A4 as planned |
| Second-person review of 180 annotations | `docs/annotation_review.md` | Pending; needs a teammate |
| Independent review of the 42 recipes, and of the 300 Instacart mapping rows | `docs/progress.md` (Phases 2–3) | Pending |
| Team literature-matrix spreadsheet | `docs/literature/` | Pending |
