# SmartCart progress and direction

## Completed

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

## Initial audit findings

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

## Current pilot and remaining data work

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

## Next implementation task

Continue in coaching mode: briefly explain each function's purpose, inputs,
outputs, and place in the pipeline; the student writes application code and the
assistant reviews and tests it. Pantry subtraction and whole-pack counts are
complete. Next, calculate a selected product option's line cost from its integer
minor-unit pack price and the required number of packs.

Build the simple basket baseline from structured requests: scale original quantities,
subtract explicit pantry stock, select whole product packs in compatible units,
calculate cost, and independently check coverage and budget. Use manually checked
expected examples to validate the outcomes. Then expand the data and add request parsing.
Historical transaction sampling and training/validation/test manifests follow
before mining rules or fitting statistical models.

After each completed milestone, record what changed, the verification evidence,
any unresolved limitations, and the next concrete task with completion criteria.
