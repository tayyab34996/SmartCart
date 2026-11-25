# SmartCart progress and direction

The build is organised in phases defined in [BUILD_PHASES.md](BUILD_PHASES.md).
Each phase starts only with the project owner's permission.

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Repo prep, raw data, D1 scope | **Complete — 2026-11-25** (one external input outstanding: the team literature matrix) |
| 1 | Fix inherited defects (D3, D4, D5) | **Complete — 2026-11-25** |
| 2 | D2 full catalog and recipes | **Complete — 2026-11-25** (independent recipe review pending) |
| 3 | D2 transaction sample and Track B splits | **Complete — 2026-11-25** (mapping review by a single reviewer) |
| 4–12 | See BUILD_PHASES.md | Not started; awaiting permission (Phase 4 is next) |

## Phase 3 — D2 transaction sample and Track B splits (complete, 2026-11-25)

**What changed**

- **Code:**
  - `src/smartcart/data/instacart.py`: hash-based user sampling, the Track B split,
    chunked order-product streaming, ordered mapping rules, and review scoring with
    Wilson intervals.
  - `scripts/prepare_transactions.py`: builds everything, profiles time and memory,
    and writes the checks. `--check` verifies reproducibility.
  - `configs/instacart_sample.json`: seed 20261125, 10,000 users, at least 5 usable orders.
- **User sample:** `data/splits/instacart_users.json`.
  - Usable orders are prior or train orders; the 75,000 test orders have no product rows.
  - 175,072 users are eligible; 31,137 are excluded for having 3–4 usable orders.
  - 10,000 users are taken in ascending `sha256(seed:user_id)` order, with no RNG library involved.
- **Track B manifest:** `data/splits/instacart_trackb.json`. For each user the last
  usable order is test, the one before is validation, and the rest are training:
  163,626 / 10,000 / 10,000 orders. Baskets are product sets; cart position and the
  reorder flag are dropped.
- **Ingredient mapping:**
  - `configs/instacart_ingredient_map.csv` holds 119 ordered rules, each with aisles,
    an include pattern and an exclude pattern.
  - `data/processed/instacart_ingredient_map.csv` maps **3,288 Instacart products to
    all 118 catalog ingredients**, covering all 98 recipe ingredients.
  - Mapped products are 21.4% of sampled item rows, and about 74% of sampled orders
    contain one. No catalog product is matched to Instacart, because catalog products
    are simulated.
- **Mapping review** (`data/processed/instacart_mapping_review.csv`): after two
  development rounds the rules were frozen. Held-out results:
  - precision 134/150 = **89.3%** (95% CI 83.4–93.3%);
  - 3/150 unmapped products are misses, which implies about 90% recall within the rule aisles.
- **Redistribution:** Instacart product names and basket contents are not committed.
  The tracked files hold IDs only. A readable mapping and the sampled item rows are
  written to the ignored `data/interim/instacart/`.
- **Docs:** `docs/data_card.md` has a new section with the sampling, split, exclusions,
  mapping policy, coverage and review.

**Verification evidence**

- `prepare_transactions.py`: all 6 checks pass (`results/metrics/transaction_checks.json`).
  Runtime is about 17 s, with process RSS at most 266 MB at the sampled steps. The
  32.4 M prior rows are streamed in 17 chunks.
- `prepare_transactions.py --check`: the user manifest, the Track B manifest and the
  mapping all rebuild byte-for-byte.
- `pytest`: **92 passed, 95 subtests** (76 before, plus 16 in `tests/unit/test_instacart.py`).
  The new tests cover:
  - sampling determinism, order independence and the too-few-users error;
  - split boundaries and test-set exclusion;
  - chunked streaming, de-duplication and dropped columns;
  - rule order, aisle restrictions and near-miss exclusions;
  - Wilson intervals;
  - consistency of the committed manifests (hash, coverage, no order in two splits);
  - the review matching the current mapping;
  - a rebuild from the archive (skipped when the archive is absent).

**Open limitations**

- The mapping review was done by **one reviewer** (the build agent). A teammate should
  re-judge the 300 held-out rows. The 16 known errors and 3 misses are deliberately left
  unfixed; any rule change needs a new held-out review.
- Recall was estimated only in the aisles that rules name, and products are not weighted
  by purchase frequency.
- Some ingredients have very few Instacart products (beef tenderloin and onion salt 1
  each; chicken cutlet and cooked brown rice 3 each), so their history signal will be sparse.
- 31,137 users with fewer than 5 usable orders are outside the sample by design.

## Phase 2 — D2 full catalog and recipes (complete, 2026-11-25)

**What changed**

- **New catalog** `data/processed/catalog.json`, built by `scripts/prepare_data.py` from
  reviewed inputs:
  - `data/processed/recipes.csv`
  - `data/processed/recipe_lines.csv`
  - `data/processed/ingredients.csv`
  - `data/processed/synonyms.csv`
  - `configs/catalog_build.json`

  The pilot catalog is unchanged, and all 20 pilot products and 3 pilot recipes carry
  over into the full catalog unchanged.
- **Recipes: 42 across 27 meal families.**
  - Food.com candidates were filtered for structure and popularity, with pork and
    alcohol excluded (a reversible design choice for the PKR context).
  - **51 recipe pages were checked on food.com:** 39 accepted, 12 rejected for lines
    that could not be converted without inventing amounts.
  - Units come from the pages, because the dataset has none and its quantity lists are
    misaligned for "X or Y" lines. Servings come from the dataset.
- **Ingredients:** 118 canonical ingredients (98 used in recipes, 20 distractors for
  retrieval near-misses) with **167 reviewed aliases**. These include British and
  Urdu-transliteration aliases such as dahi, aloo, pyaz, chanay and atta.
- **Products: 466 simulated options.**
  - Fictional house brands (Basics, Select, Organic), several pack sizes per ingredient,
    PKR prices in minor units.
  - 12 dietary variants: vegetarian cheddar, gluten-free tamari, vegan mayonnaise and others.
  - 4 deterministic unavailable products.
- **Conversions:** NIST lb, oz, cup, tbsp and tsp, plus 24 ingredient-specific
  King Arthur weight-chart estimates. The project policy for dash and pinch is documented.
- **Code:**
  - `validate_catalog()` and `load_catalog()` in `data/contracts.py` (pilot contract plus `meal_family`);
  - `data/catalog_build.py` (deterministic build);
  - `data/catalog_checks.py` (coverage, duplicate, missing-field and target checks);
  - `scripts/prepare_data.py` (`--check` verifies the catalog is reproducible).
- **Docs:**
  - `docs/data_card.md`: sources and terms, selection, the full line-resolution policy,
    the simulation and dietary policies, and known gaps.
  - `BUILD_PHASES.md`: corrected the dietary-value wording to `allowed` / `disallowed` / `unknown`.

**Verification evidence**

- `scripts/prepare_data.py`: all checks pass. The results are in `results/metrics/catalog_checks.json`:
  - recipes ≥ 38, meal families ≥ 20, products within 300–500;
  - every recipe line is covered by an available product;
  - no duplicate product names and no missing fields.
- `prepare_data.py --check`: the committed catalog rebuilds byte-for-byte.
- `pytest`: **76 passed, 95 subtests** (63 before, plus 13 catalog tests). The new tests cover:
  - reproducibility and the scope targets;
  - pilot preservation and line coverage;
  - exact converted amounts (2 cups cheddar = 226 g; 16 oz = 453.593 g; 1 bunch = 6 stalks; 2 pinches = 0.617 ml);
  - serving scaling;
  - distractors, dietary variants and labels;
  - Basics availability and simulation labelling;
  - the meal-family contract;
  - the price helper.
- The cheapest complete basket at base servings ranges from PKR 500 (pasta dough) to
  PKR 9,990 (4 lb beef tenderloin). Every recipe is purchasable.

**Open limitations**

- **Independent review is pending** for all 42 recipes and for the `agent_reviewed`
  ingredient mappings. A teammate should spot-check lines against the pages.
- Lines were checked against fetched page text; servings are from the dataset.
- There is no stew or stir-fry family: those candidates needed volume-to-mass conversions
  for chopped vegetables, which no cited source covers.
- Spices, condiments and purées are stocked by volume, a simulation simplification.
- **Bug found for Phase 7:** `retrieval/filtering.py` checks dietary values with `is True`,
  but the catalog uses `"allowed"`, so no product can pass a dietary filter.
- Pilot products keep all-`unknown` dietary labels, so they never satisfy a hard diet request.

## Phase 0 — Repo prep, raw data, D1 scope (complete, 2026-11-25)

Phase 1 was done first, at the owner's request.

**What changed**

- **Raw data restored.** `data/raw/archive_3.zip` (Instacart) and `data/raw/archive_4.zip`
  (Food.com) are back in place. Their SHA-256 hashes match the original audit exactly:
  `c347cd7f…3038` and `fa7910c9…527d`.
- **Audit re-run.** `scripts/audit_data.py` took 243 s and regenerated
  `docs/data_audit.md`, `data/interim/audit/summary.json` and `recipe_candidates.csv`.
- **`.gitignore`** now tracks `data/processed/catalog.json`, `data/annotations/*.jsonl`,
  `data/benchmarks/*.json`, `data/splits/*.json`, `results/metrics/` and
  `results/run_manifest.json`. Raw archives, audit intermediates and `models/` stay ignored.
- **D1 scope.** Added `docs/scope.md`: user scenario, pipeline, core and out-of-scope items,
  the simulated-price policy, contribution statement, RQ1–RQ3, definition of success,
  Tracks A and B, and the unresolved 90% rubric note.
- **Literature skeleton.** Added `docs/literature/review.md`: the 15-row comparison table
  with the six closest papers from the plan [S7]–[S12] pre-listed (analysis cells empty
  until each paper is read), completion rules and the synthesis outline.

**Verification evidence**

- The regenerated `docs/data_audit.md` is identical to the committed version except for
  the `Generated:` timestamp. Every count, hash and check reproduced:
  - Instacart: 49,688 products, 3,421,083 orders, 32,434,489 prior rows and 1,384,617 train rows.
  - Food.com: 522,517 recipes.
- `git check-ignore` confirms the new data and result paths are tracked, and that
  `data/raw/`, `data/interim/` and `models/` remain ignored.
- `pytest`: 63 passed, 95 subtests.

**Open items**

- **External input:** the team's literature-matrix spreadsheet must be added to
  `docs/literature/`. Rows 7–15 and all analysis cells wait on it and on reading the papers (Phase 12).
- The rubric's missing 10% is to be confirmed with the instructor (see `docs/scope.md`).

## Phase 1 — Fix inherited defects (complete, 2026-11-25)

**What changed**

- **D3 pantry bug.** Reference scenario `d3_ref_02` now uses pantry key
  `white_flour` (was `'flour'`, which matched nothing, so pantry stock was ignored).
  The 250 g in the pantry now covers the 120 g requirement, so no flour is bought.
- **D3 basket assembly** (`optimization/basket.py`):
  - A line fully covered by the pantry returns `line_status: covered_by_pantry`, with 0 packs and 0 cost.
  - An ingredient with no compatible product returns `line_status: no_compatible_option`, and the basket status becomes `incomplete`, instead of raising. The uncovered IDs are listed in `uncovered_ingredients`.
  - Every line now carries its `ingredient_id`. `item_count` counts purchased lines only.
- **D3 unmatched pantry keys** (`pipeline/baseline.py`): the basket lists `ignored_pantry_keys`, so a misspelled pantry ingredient is visible instead of silently ignored.
- **D3 evaluator** (`pipeline/evaluator.py`):
  - A scenario passes only if status, maximum cost, the **exact total**, **every expected line** (ingredient, product, packs, line cost) and pantry use all match.
  - All 5 reference scenarios now carry hand-calculated expected lines and totals (`benchmarks/reference.py`, with the calculation in its header comment).
  - Scenario `d3_ref_05` was renamed to say honestly that it does not exercise multiple packs.
- **D4 unsupported figure.** Deleted `results/figures/10_nlu_training_and_comparison_curves.png` and its notebook 04 display cell. No committed code trained DistilBERT or produced it. It is regenerated from real logs in Phase 6.
- **D5 answer leak** (`retrieval/evaluation.py`): the evaluator no longer passes the gold `required_ingredient` to the eligibility filter. Rankings are scored over the whole catalog; only request-side constraints (unit, diet) are applied.
- **D5 TF-IDF** (`retrieval/tfidf.py`): ranks the whole catalog deterministically (score, then product ID) and keeps zero-score items, so both retrievers return equal-length lists.
- `results/figures/README.md`: figure 10 is marked as removed and figure 11 as superseded.

**Verification evidence**

- `pytest`: **63 passed, 95 subtests** (55 before, plus 8 new regression tests).
  - Pantry stock reduces purchased flour (1 pack → 0).
  - A wrong expected line fails a scenario.
  - A wrong expected total fails a scenario.
  - An unmatched pantry key is reported and fails a scenario.
  - A missing product option gives an `incomplete` basket.
  - The retrieval evaluator never receives the gold ingredient.
  - A wrong-ingredient product ranked first is penalised (MRR 0.5).
  - TF-IDF returns a deterministic full-length ranking.
- `results/predictions/baseline_outputs.json` re-exported: 5/5 scenarios pass the stricter checks. The pantry scenario total is now 41000 minor units (was 50000).
- `results/predictions/retrieval_benchmark_results.json` re-run with the fixed evaluator. Test split, before → after the fix:

  | Retriever | Recall@10 | MRR |
  | --- | --- | --- |
  | MiniLM | 0.957 → 0.957 | 0.960 → 0.848 |
  | TF-IDF | 0.450 → 0.690 | 0.450 → 0.491 |

**Open limitations (carried to later phases)**

- The retrieval numbers above are **provisional**. Dev and test queries share the same 11 pilot ingredients, and the catalog has only 20 products. The grouped split and full catalog come in Phases 4 and 7. Do not cite these numbers or figure 11 in the report.
- Figure 09 (intent confusion matrix) also has no committed plotting code; it is regenerated in Phase 6.
- The NLU metrics in `results/predictions/nlu_evaluation_results.json` are still from 8 training examples, and the DistilBERT models remain untrained (Phase 6).
- The baseline still uses keyword intent rules and matches products by ingredient ID without a retrieval step (Phase 5).

## Earlier history (before the phase plan)

### Completed

- Read the proposal, build plan, and literature matrix; established the project scope.
- Initialized the local checkout and project structure.
- Compared candidate datasets and documented source limitations.
- Located the user-supplied Instacart and Food.com ZIP files.
- Implemented and ran a reproducible source audit with six passing correctness tests.
- Recorded archive SHA-256 hashes, file inventory, source columns, and quality checks.
- Scanned all six Instacart CSVs and the complete Food.com recipe CSV.
- Created a private 50-recipe review shortlist; all candidates remain unverified.
- Defined executable ingredient, conversion, product, recipe, and provenance contracts.
- Added three separately source-checked recipe examples, eleven canonical ingredients,
  and twenty simulated product options covering all twelve recipe lines.
- Preserved gram/millilitre/piece distinctions, documented flour conversion assumptions,
  and marked all three independent recipe reviews as pending.
- Ran all 18 unit tests successfully, including 12 pilot-contract tests, and checked
  the scaled-requirements CLI on the seed.
- The student implemented `packs_needed()` and `missing_amount()`; both passed
  their boundary and decimal-arithmetic checks on 21 October 2026.
- Added seven regression tests covering those helpers and their composition.
  The combined suite now contains 25 passing tests.
- The student implemented `line_cost_minor()`; review added explicit integer-type
  validation before comparisons, including rejection of booleans. Six cost tests
  cover boundaries, types, precision, and pantry-to-pack-to-cost composition.
  The combined suite now contains 31 passing tests.
- The student implemented `evaluate_product_option()` and corrected catalog-key
  lookups and local-variable handling through review. Seven option tests verify
  quantities, packs, price, surplus, incompatible inputs, unchanged catalog records,
  and two actual seed products. The combined suite now has 38 passing tests.

- Later work by member 1 (before 2026-11-25): baseline pipeline and benchmark (D3),
  NLU skeleton (D4) and retrieval (D5). See BUILD_PHASES.md section 2 for its status.
- 2026-11-25: Python 3.11 `.venv`, completed `requirements.txt` and a verified
  `requirements-lock.txt`. Raw archives restored to `data/raw/`; their SHA-256 hashes
  match the audit below exactly.

### Initial audit findings

The supplied Instacart files contain 206,209 users, 3,421,083 orders, 49,688
products, 32,434,489 prior purchase rows, and 1,384,617 training purchase rows.
Primary-key, product/category reference, order reference, cart-position, and
duplicate basket-item checks passed within the documented audit scope.

Food.com contains 522,517 recipes. Of those, 407,537 (77.99%) have mismatched
ingredient and quantity list lengths, and 182,911 have missing or invalid servings.
Only 48,339 pass the current structural checks before unit review. These are
overlapping checks, and none of these counts establishes optimizer readiness.
The recipe CSV has no dedicated ingredient-unit column.

Evidence: [audit report](data_audit.md), [source dictionary](data_dictionary.md),
and the ignored `data/interim/audit/summary.json` and `recipe_candidates.csv` files.

### Pilot data work (superseded by Phase 2)

The first examples and [their contracts](pilot_data.md) are implemented. They are
development data, not locked benchmark examples. Simulated product prices and
attributes are declared explicitly. No Instacart/Open Food Facts SKU joins or
product dietary claims have been established.

The original five-recipe target currently has three source-checked examples.
One is pasta dough rather than a complete dinner. Add two more usable meal
recipes, complete independent review, and write five expected basket examples.
The original acquisition plan below remains the acceptance checklist:

1. Define the recipe, ingredient, product, mapping, and review/provenance columns.
2. Review five suitable meal recipes from the shortlist against recorded sources.
   Verify servings, quantity-to-ingredient attachment, units, alternatives, and
   pantry assumptions. Reject unresolved records; do not guess missing units.
3. Create canonical ingredient IDs and reviewed synonyms.
4. Assemble 20 product options that cover the accepted recipes, with explicit pack
   sizes, compatible units, dietary evidence or unknown status, and fixed simulated
   prices in one currency.
5. Check recipe-to-product mapping coverage and define five structured requests
   with manually calculated expected quantities, pack counts, and totals.

Completion evidence: five accepted recipes, a covering 20-option catalog,
reviewed mappings, and five expected basket examples. No recipe is marked
ready while its required quantities or units remain unresolved.

## Next task (awaiting permission)

**Phase 4 — D2 benchmarks and gold feasibility checker.**

- `data/annotations/nlu.jsonl` (900 examples) with a grouped 600/150/150 split by `seed_id`.
- A second-person check of at least 20% of the annotations, or a disclosed delayed self-review.
- `src/smartcart/validation/feasibility.py`: an exhaustive gold feasibility checker
  over the full catalog.
- Basket scenarios (`basket_dev.json`, `basket_test.json`) and a grouped retrieval benchmark.

With Phase 3 done, Phase 8 (associations and Track B) needs only Phase 7.
Completion criteria are in [BUILD_PHASES.md](BUILD_PHASES.md).

After each phase, record what changed, the verification evidence, the open
limitations and the next task here.
