# SmartCart

Conversational grocery basket planning with semantic search and constraint-aware recommendation.

The source-data audit and pilot data contracts are implemented. The reviewed seed
contains three source-checked recipes, eleven canonical ingredients, and twenty
explicitly simulated product options. Local Instacart and Food.com ZIP files are
kept outside version control. Basket generation, language models, and experimental
results have not been implemented yet.

Dataset research and the next data milestone are documented in
[dataset selection](docs/dataset_selection.md), [data organization](data/README.md),
and [source data dictionary](docs/data_dictionary.md).

## Audit the downloaded data

The audit uses the Python standard library and requires Python 3.11 or newer.
From the repository root, run:

```powershell
python scripts/audit_data.py --config configs/data_audit.json
```

Update archive paths in the configuration if your filenames differ. The command
reads the original ZIP files in place, hashes them, scans all six Instacart CSVs
and Food.com's recipe CSV, and writes [the audit report](docs/data_audit.md).
Machine-readable checks and a recipe review shortlist are saved under
`data/interim/audit/`, which is ignored by Git. Review CSV and Parquet files are
inventoried without a full scan. No missing recipe units are guessed.

Run the audit's correctness tests with:

```powershell
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

## Inspect the pilot data

The [pilot contracts and source notes](docs/pilot_data.md) explain the schemas,
quantity conversions, simulation policy, and pending independent recipe review.

```powershell
python scripts/validate_pilot.py
python scripts/validate_pilot.py --recipe foodcom_3474 --servings 2
```

These commands validate the seed and calculate ingredient requirements. They do
not yet choose product packs or enforce a budget. Product prices and pack options
are simulated; dietary suitability is unknown, and no external SKU matches are
claimed. A documented flour conversion is an ingredient-specific reference estimate.

Next, build the structured-request basket baseline and add two more source-checked
meal recipes to reach the original five-recipe milestone.
See [progress and next steps](docs/progress.md) for completion criteria.

The student's first two quantity helpers are implemented: `missing_amount()`
subtracts pantry stock without negative demand, and `packs_needed()` rounds up
to whole packs. Their regression checks are included in the unit suite above.

## Project structure

```text
SmartCart/
|-- configs/                 # Data, model, and experiment configuration
|-- data/
|   |-- raw/                 # Original source data
|   |-- external/            # Supporting data from external sources
|   |-- interim/             # Intermediate preparation outputs
|   |-- processed/           # Prepared catalog, recipes, and transactions
|   |-- annotations/         # Intent and slot annotations
|   |-- benchmarks/          # Retrieval and basket evaluation cases
|   `-- splits/              # Fixed train, validation, and test manifests
|-- docs/
|   |-- literature/          # Literature review and research notes
|   `-- report/              # Final report material
|-- models/                  # Model checkpoints and retrieval indexes
|-- notebooks/               # Exploratory analysis and training notebooks
|-- results/
|   |-- metrics/             # Evaluation summaries
|   |-- predictions/         # Saved predictions and basket traces
|   `-- figures/             # Report plots
|-- scripts/                 # Data preparation, training, and evaluation entry points
|-- src/
|   `-- smartcart/
|       |-- data/            # Data loading, preparation, and ingredient mappings
|       |-- nlu/             # Intent detection, slot extraction, and normalization
|       |-- recipes/         # Recipe resolution and quantity calculation
|       |-- retrieval/       # Lexical and semantic product search
|       |-- associations/    # Basket patterns and history-based scoring
|       |-- optimization/    # Constrained product and pack selection
|       |-- validation/      # Independent basket checks
|       |-- explanations/    # Explanations from verified basket records
|       |-- pipeline/        # End-to-end orchestration and conversation state
|       |-- evaluation/      # Baselines, metrics, and experiment execution
|       `-- ui/              # Streamlit interface components
`-- tests/
    |-- unit/                # Component correctness tests
    |-- integration/         # Pipeline and interface integration tests
    `-- fixtures/            # Small deterministic test inputs
```

Empty directories contain `.gitkeep` placeholders so Git can track the structure.
Raw datasets, model artifacts, and generated results are excluded from version control.
The small curated `data/processed/pilot/catalog.json` seed is explicitly included.
