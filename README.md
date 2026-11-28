# SmartCart

SmartCart is an **offline grocery-basket assistant**, built as a university course project.
A shopper types a request in plain English, for example *"Plan honey lime chicken for 3
people, budget 3000 rupees"*. SmartCart turns it into a complete basket of whole product
packs that covers every ingredient, subtracts what the shopper already has, respects diets
and exclusions, and stays within the budget. If the request is ambiguous it asks a short
question; if no valid basket exists it says so and proves it, rather than returning a
basket that breaks the rules.

> **Prices are simulated.** The 466-product catalog uses simulated prices in Pakistani
> rupees (PKR). The results compare methods offline; they say nothing about real
> supermarket prices or savings.

The pipeline: **parser** (rules + TF-IDF/LinearSVC baseline, or fine-tuned DistilBERT) →
structured request → **retrieval** per ingredient (TF-IDF or MiniLM + exact FAISS) →
**selection** (cheapest option per line with post-hoc filtering, or OR-Tools CP-SAT with
the hard rules applied before selection) → an independent **validator** → explanations.
Association rules mined from Instacart orders give optional history and pair scores, and
are evaluated separately on next-basket ranking (Track B).

The report is in [`docs/report/`](docs/report/). Progress, decisions and verification for
every phase are in [`docs/progress.md`](docs/progress.md).

## Results at a glance (locked test split, evaluated once)

| Question | Result |
| --- | --- |
| Constrained selection vs independent ranking (RQ2) | With the gold request, CP-SAT gives 200/200 correct outcomes against 182/200 for E0; +0.090 [+0.064, +0.117] (paired bootstrap over families) |
| Semantic vs lexical retrieval (RQ1) | MiniLM Recall@10 0.764 vs TF-IDF 0.610 on 100 free-text queries; no effect on baskets |
| Association-aware scoring (RQ3) | No effect on baskets; on next-basket ranking it lowers NDCG@10 by 0.0105 [−0.0122, −0.0089] |
| End to end | The rule-based parser with CP-SAT (A1) is best: 192/200, 0 rule violations. DistilBERT runs (E4): 164–168/200 |

Full tables: [`results/tables/`](results/tables/). Failure cases:
[`docs/failure_analysis.md`](docs/failure_analysis.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `src/smartcart/` | The package: `data`, `benchmarks`, `nlu`, `retrieval`, `associations`, `optimization`, `validation`, `explanations`, `pipeline`, `app` |
| `scripts/` | One command per pipeline step, each with a `--check` flag that rebuilds in memory and compares with the committed outputs |
| `configs/` | Frozen configurations; `configs/experiments/` holds the runs E0–E4 and A1–A4 |
| `data/processed/` | Catalog (466 products, 118 ingredients, 42 recipes), recipes, synonyms, mappings, association rules |
| `data/annotations/`, `data/benchmarks/`, `data/splits/` | 900 annotated requests, basket and retrieval benchmarks, split manifests; test files locked in [`docs/benchmark_lock.md`](docs/benchmark_lock.md) |
| `results/` | Predictions, metrics, report tables, figures, and `run_manifest.json` |
| `app.py` | Streamlit interface |
| `tests/` | Unit and integration tests (`pytest`) |
| `notebooks/` | Early exploratory notebooks (Instacart EDA, first prototypes); not part of the reported results |

## Setup

Everything runs on a CPU. The commands are for **Windows PowerShell** from the repository
root; on Linux or macOS use `python3.11 -m venv .venv` and `.venv/bin/python`.

1. **Python 3.11** and a short path (for example `C:\SmartCart`): Windows' 260-character
   path limit breaks the PyTorch install in deep folders.

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python -m pip install --upgrade pip
   .\.venv\Scripts\python -m pip install -r requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
   ```

   `requirements-lock.txt` pins every package (tested with Python 3.11.9);
   `requirements.txt` lists the direct dependencies.

2. **Hugging Face models** (no account needed), pinned to the revisions the project used:

   ```powershell
   $env:HF_HUB_DISABLE_XET = "1"
   .\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('sentence-transformers/all-MiniLM-L6-v2', revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41')"
   .\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('distilbert/distilbert-base-uncased', revision='12040accade4e8a0f71eabdb258fecc2e7e948be', allow_patterns=['config.json','tokenizer.json','tokenizer_config.json','vocab.txt','model.safetensors'])"
   ```

   The code then loads both offline.

3. **Fine-tuned DistilBERT checkpoints** (about 1.5 GB, not on GitHub). Either get the
   team's copy and place it so that `models\nlu\transformer\seed{13,42,7}\{intent,slots}\model.safetensors`
   exist, or retrain them (about 75 minutes on a 4-thread CPU):

   ```powershell
   .\.venv\Scripts\python scripts/train_nlu.py
   ```

   Retrained weights differ slightly from the team's, so the DistilBERT results would not
   reproduce byte for byte. `results/run_manifest.json` records the SHA-256 of the team's
   checkpoints. Without checkpoints, the app falls back to the baseline parser and the
   DistilBERT tests are skipped.

4. **Raw data** (not redistributed; see the terms below). Download from Kaggle and save
   with these names:

   | File | Dataset | SHA-256 |
   | --- | --- | --- |
   | `data\raw\archive_3.zip` | [Instacart Market Basket Analysis](https://www.kaggle.com/c/instacart-market-basket-analysis/data) | `c347cd7f…db03038` |
   | `data\raw\archive_4.zip` | [Food.com Recipes and Reviews](https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews) (irkaal) | `fa7910c9…b7527d` |

   The full hashes are in [`docs/data_audit.md`](docs/data_audit.md). Then rebuild the
   Instacart working files (git-ignored, about 20 seconds):

   ```powershell
   .\.venv\Scripts\python scripts/prepare_transactions.py
   ```

   The raw data is only needed for the Instacart sample, association mining and Track B.
   The catalog, benchmarks and annotations are committed.

[`docs/TEAMMATE_SETUP.md`](docs/TEAMMATE_SETUP.md) has the same steps with every check.

## Reproducing the results

Each script rebuilds its committed outputs; with `--check` it rebuilds in memory and
reports `same` or `DIFFERS` for every file.

| Step | Command | Outputs |
| --- | --- | --- |
| Catalog and recipes | `scripts/prepare_data.py` | `data/processed/catalog.json` and tables |
| Instacart sample, Track B split | `scripts/prepare_transactions.py` | `data/splits/instacart_*.json`, mapping |
| Annotations and benchmarks | `scripts/build_benchmarks.py` | `data/annotations/`, `data/benchmarks/` |
| E0 baseline (dev) | `scripts/run_baseline.py` | `results/metrics/E0_*` |
| DistilBERT training / evaluation | `scripts/train_nlu.py`, `scripts/evaluate_nlu.py` | checkpoints, `results/metrics/nlu_*` |
| MiniLM index | `scripts/build_index.py` | `results/metrics/retrieval_index.json`, local cache |
| Retrieval (dev) | `scripts/evaluate_retrieval.py` | `results/metrics/retrieval_dev.json` |
| Association rules, Track B (validation) | `scripts/mine_rules.py`, `scripts/evaluate_trackb.py` | `data/processed/rules.csv`, `results/metrics/trackb_validation.json` |
| CP-SAT selection (dev) | `scripts/run_solver.py` | `results/metrics/solver_dev.json` |
| **All test-split experiments** | `scripts/evaluate_all.py` | `results/predictions/runs/`, `results/metrics/runs/`, `results/tables/`, figures 14–18 |
| One experiment | `scripts/evaluate.py --config configs/experiments/E4.json` | that run's rows and metrics |
| Run manifest | `scripts/make_manifest.py` | `results/run_manifest.json` |

Prefix each command with `.\.venv\Scripts\python`. To verify a checkout without changing
anything:

```powershell
.\.venv\Scripts\python scripts/evaluate_all.py --check     # about 30 minutes
.\.venv\Scripts\python scripts/make_manifest.py --check    # also checks installed versions and raw-data hashes
.\.venv\Scripts\python -m pytest -q
```

The test split is locked: it was evaluated once, with frozen configurations. `--check`
re-reads it only to confirm that the committed results reproduce. Do not tune anything on
it.

## The interface

```powershell
.\.venv\Scripts\python -m streamlit run app.py
```

The first load takes about half a minute while the models load. Six demonstration
conversations are in `configs/app.json` and can be replayed with
`scripts/run_demo_cases.py`. Sample inputs:

- `Plan honey lime chicken for 3 people, budget 3000 rupees`, then
  `Actually, can we do it for 1,200 rupees instead` (proven infeasible, with the minimum budget)
- `Something vegetarian for dinner for 3, keep it under 2500 rupees` (suggests dishes to confirm)
- `Get me everything for potato soup for 4 people within 2000 rupees, I already have some onion`
  (asks how much onion), then `I have 2 onions`
- `mates coming round tonight lol, fancy doing baked salmon, there'll be 6 of us and I can't spend more than 10000`
- `Plan baked salmon for 6 people under 500 rupees` (proven infeasible)

The interface supports the 42 catalog recipes and grocery lists of catalog ingredients.

## Data sources and terms

- **Instacart Market Basket Analysis** (Kaggle). The provider's terms allow
  non-commercial use and restrict redistribution
  ([provider terms](https://gist.github.com/jeremystan/582eba13d6ee27ed465c43dc78934700)).
  The pipeline commits only derived data: product, order and user IDs, the
  product-to-ingredient mapping, counts and ingredient-level association rules. Basket
  rows with product names stay in the git-ignored `data/interim/`.
  - **Exception, inherited from before the phase plan:** `data/processed/cleaned_instacart_data.csv`
    and `scaled_features.csv` (100,000 order-product rows from the early EDA notebooks,
    with product names) are in the repository. No reported result uses them. Whether they
    may stay in a public repository under the provider's terms is an open question for
    the team.
- **Food.com Recipes and Reviews** by irkaal (Kaggle; labelled CC0 on Kaggle). Recipe IDs
  and servings come from it; amounts and units were taken from each recipe's food.com
  page (recipe text belongs to its authors; used for non-commercial coursework).
- **Catalog:** products, pack sizes and prices are simulated and flagged per attribute in
  `simulated_fields`. Dietary labels are `allowed`, `disallowed` or `unknown`, and
  `unknown` never satisfies a diet.
- Unit conversions follow NIST SP 811; cup-to-gram estimates follow the King Arthur
  Baking ingredient weight chart.

Details: [`docs/data_card.md`](docs/data_card.md) and
[`docs/dataset_selection.md`](docs/dataset_selection.md). The code is under the MIT
license ([`LICENSE`](LICENSE)); the data licenses are separate.
