# SmartCart data

Dataset research and the recommended sources are documented in
[dataset selection](../docs/dataset_selection.md). The user has supplied these
downloaded source archives:

| Local file | Identified contents |
| --- | --- |
| `raw/archive_3.zip` | Instacart's six order, product, aisle, and department CSVs. |
| `raw/archive_4.zip` | Food.com recipes and reviews in CSV and Parquet formats. |

The archives retain their downloaded filenames and are not modified or extracted
by the audit. File hashes and inventory are saved in
`interim/audit/summary.json` after a successful run. The actual download date and
publisher checksums have not been independently established.

## Organization

| Folder | Intended contents |
| --- | --- |
| `raw/` | Downloaded archives, currently `archive_3.zip` and `archive_4.zip`. |
| `raw/instacart/` | Reserved for original individual CSVs if extraction is needed later. |
| `external/unitools/` | Pinned recipe snapshot and its source/license metadata, when acquired. |
| `external/foodcom/` | Reserved for original individual recipe files if extraction is needed later. |
| `external/openfoodfacts/` | Targeted product snapshot and source/license metadata. |
| `external/openprices/` | Optional dated price observations. |
| `interim/audit/` | Machine-readable source inventory, full CSV checks, and an unverified recipe shortlist. |
| `processed/` | Reviewed catalog, recipes, ingredients, and mapping tables. |
| `processed/pilot/catalog.json` | Versioned development seed: three source-checked recipes, eleven ingredients, twenty simulated products, and conversion/source records. |
| `annotations/` | Reviewed intent and slot annotations. |
| `benchmarks/` | Retrieval queries and feasible, infeasible, and clarification scenarios. |
| `splits/` | Frozen user/request IDs and train, validation, and test manifests. |

Subfolders other than the actual archives and audit output remain planned destinations.
Preserve source files without editing them. Record the source URL, retrieval date,
release/revision, byte size, checksum, license, and relevant access conditions at
acquisition. Store mappings and corrections separately from the originals.

Raw data and generated artifacts are ignored by Git. The small curated pilot seed
is explicitly allowed; it contains no transaction records or cooking instructions.
Do not add credentials or
restricted source records to the repository. Dataset licenses remain separate
from the code license.

## Reproduce the audit

From the repository root:

```powershell
python scripts/audit_data.py --config configs/data_audit.json
```

The audit reads all six Instacart CSVs and `recipes.csv` from Food.com's ZIP.
It inventories the remaining members but does not scan reviews or Parquet data.
Only the standard library is required. Large files are streamed; order IDs use a
bounded byte lookup with an explicit maximum ID of 50 million. Malformed CSV
structure or nonnumeric identifiers fail explicitly rather than silently changing data.

See [the generated report](../docs/data_audit.md) for measured results and coverage.
`recipe_candidates.csv` contains a deterministic shortlist for human review,
not approved recipe data. Positive amounts and matching list lengths do not
establish units. Every candidate starts with `optimizer_ready=False`.

## Curated pilot

See [the pilot schemas and source checks](../docs/pilot_data.md). Validate the seed
or inspect scaled ingredient requirements with:

```powershell
python scripts/validate_pilot.py
python scripts/validate_pilot.py --recipe foodcom_3474 --servings 2
```

The three admitted recipe examples have source-page checks, with independent
review pending. The original raw audit shortlist remains an unverified discovery
artifact. No generic gram/millilitre/piece conversion is assumed.

Next milestone: build and check the structured-request basket baseline; add two
more source-checked meal recipes before expanding to the larger catalog and benchmark.
