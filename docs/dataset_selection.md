# SmartCart dataset selection

Research date: 20 October 2026.

Status: initial source research completed. The user has since supplied Instacart
and Food.com ZIPs; see [the local data guide](../data/README.md) and
[the full CSV audit](data_audit.md) for acquisition and quality evidence. Original
recommendations below remain research judgments, not measured model results;
source access notes describe the research session before the user supplied files.

## Recommended combination

Use separate sources for transactions, recipes, product attributes, and evaluation.
No source inspected supplies all four with reliable joins, quantities, and prices.

| Layer | Recommended source | Decision |
| --- | --- | --- |
| Purchase histories | Instacart Online Grocery Shopping Dataset 2017 | Primary transaction choice, subject to obtaining the files through an available access route. |
| Quantity-aware recipes | A manually reviewed SmartCart subset; inspect UniTools first and use Food.com for supplementary discovery | Start with 5 accepted recipes; expand toward 40 only after units, servings, and mappings pass review. |
| Product attributes | Open Food Facts | Optional enrichment for individually verified products; insufficient as an automatic dietary validator. |
| Purchasable catalog and prices | A curated SmartCart catalog with documented pack sizes and fixed, explicitly simulated prices | Required integration layer. Start with 20 product options; expand toward 300–500 after the pilot. |
| Language and basket benchmarks | SmartCart annotations and independently reviewed scenarios | Required because the inspected sources do not contain our complete request/constraint labels. |

Suggested counts are planning targets. They are not counts of collected or usable data.

## 1. Instacart: primary transaction source

- Purpose: frequent itemsets, co-purchase rules, reorder analysis, and optional historical ranking.
- Scale: the provider describes over 3 million orders and over 200,000 users.
- Required files: `orders.csv`, `order_products__prior.csv`,
  `order_products__train.csv`, `products.csv`, `aisles.csv`, and `departments.csv`.
- The provider dictionary includes user/order sequence, product names, aisle and
  department IDs, cart position, and reorder flags. It does not provide purchased
  quantities, prices, structured pack sizes, barcodes, or authoritative dietary labels.
- Cart position and reorder flags must never be interpreted as purchased quantities.
- Begin with a deterministic sample of approximately 10,000 users after profiling;
  preserve their usable order histories and the sampled IDs.
- For local next-basket evaluation, split labeled histories chronologically before
  mining rules. The competition's unlabeled test orders are not a local gold test set.
- Access finding: the original provider download page and old Kaggle competition
  path returned 404 in this session. Search surfaced the current Market Basket
  Analysis page below. Competition file-list API requests returned HTTP 401.
  Download availability and archive contents remain unverified; do not claim acquisition.
- Terms: the original provider states non-commercial use and restrictions on
  third-party access/redistribution. Keep raw data out of the public repository;
  a mirror's license label does not replace the original provider's terms.

Sources: [provider announcement](https://tech.instacart.com/3-million-instacart-orders-open-sourced-d40d29ead6f2),
[provider data dictionary](https://gist.github.com/jeremystan/c3b39d947d9b88b3ccff3147dbcf6c6b),
[provider terms](https://gist.github.com/jeremystan/582eba13d6ee27ed465c43dc78934700),
[Kaggle access candidate](https://www.kaggle.com/competitions/basket-analysis/data).

## 2. Recipes: review quantities before choosing the final source

### Food.com — irkaal/foodcom-recipes-and-reviews

- The uploader reports 522,517 recipes and 1,401,982 reviews. Reviews are not
  required for SmartCart's core recipe-to-basket path.
- The Kaggle metadata labels the upload CC0: Public Domain. Preserve this metadata
  and the source attribution; do not assume that a metadata label independently
  establishes rights in all underlying text or images. Images are unnecessary here.
- Formats include CSV and Parquet. The uploader recommends Parquet to preserve
  schema; CSV includes R-style list strings. Never execute those strings as code.
- Direct evidence: inspected the CSV header and first five records by reading only
  the first 128 KiB of the compressed CSV download into memory.
- The header contains `RecipeIngredientQuantities`, `RecipeIngredientParts`,
  `RecipeServings`, and `RecipeYield`, but no dedicated ingredient-unit column.
- Recipe 38 lists amounts `4`, `1/4`, `1`, and `1` alongside ingredient names
  without units. Recipe 40 has six quantity entries and five ingredient entries.
  These examples are enough to reject blind positional conversion, not to estimate
  dataset-wide error rates. A full quality audit has not been performed.
- Decision: useful supplementary recipe discovery. Do not use amounts directly for
  pack optimization. Admit a recipe only after quantities, units, alignment, and
  servings are verified from a documented source. Do not invent missing units.
- Full download size is not pinned: Kaggle view and search metadata reported
  different total-byte figures, and the release includes multiple formats.
  Inspect per-file sizes before acquisition; obtain only the chosen recipe format.

Sources: [dataset page](https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews),
[live metadata API](https://www.kaggle.com/api/v1/datasets/view/irkaal/foodcom-recipes-and-reviews).

### UniTools World Recipes — promising small pilot source

- Directly inspected its full JSON in memory: version 2.0.0, generated 2 September
  2026, with 501 recipe records. No copy was saved as project data.
- Has `baseServings` and ingredient IDs, English names, quantities, units, and
  scaling labels. All 501 inspected records have a positive base-servings value.
- The inspected file contains 5,404 ingredient occurrences; 414 have null quantity
  and `toTaste` units. Other units include grams, kilograms, millilitres, litres,
  pieces, teaspoons, tablespoons, cloves, pinches, sprigs, and slices.
- Ingredient IDs require review: spelling variants and multi-ingredient names exist.
  A name such as a combined spice mixture must not be treated as a single mapped
  ingredient unless a matching purchasable blend is explicitly supported.
- The live README describes `sublinear` scaling, while the inspected file uses
  `damped`. No numerical damping function was established. Do not implement
  nonlinear scaling from that label alone.
- It is maintained by one person and is not a substitute for independently checked
  recipe quantities or dietary evidence. Nutrition is described as computed.
- Decision: inspect first for the five-recipe pilot because quantities and units are
  explicit. Accept only reviewed records with a documented scaling policy. Resolve
  vague required amounts before use, or reject the recipe. Any optional-garnish policy
  must be explicit and shared by all evaluated methods.
- License: CC BY-SA 4.0 as declared by the publisher. Retain attribution and license
  notices with derived recipe data; the repository's MIT code license does not
  replace this data license. Images have separate per-image terms and are unnecessary.

Sources: [publisher repository](https://github.com/farcrak/unitools-recipes),
[versioned JSON copy inspected](https://raw.githubusercontent.com/farcrak/unitools-recipes/main/unitools-recipes-v1.json),
[publisher dataset page](https://theunitools.com/en/data).

## 3. Open Food Facts: product enrichment

- The official field definitions include product names, quantity, normalized product
  quantity, ingredients, allergens, traces, labels, and ingredient-analysis tags.
- Use a small targeted snapshot rather than a global database dump. Require product
  identity and usable pack units before admitting an option to the catalog.
- Missing allergen or diet information means unknown, not safe. Product labels and
  automated ingredient analysis need a documented evidence policy.
- Instacart product IDs are not Open Food Facts barcodes. Name similarity alone does
  not prove two records describe the same SKU. Keep reviewed mappings and provenance.
- Fresh produce and local product coverage must be profiled; no Pakistan-specific
  completeness or catalog overlap rate was measured in this session.
- Database license: ODbL, with attribution/share-alike conditions. Preserve source
  separation and licenses; do not publish a combined restricted Instacart/OFF dump.

Sources: [official field definitions](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/html/data-fields.txt),
[official license guidance](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/tutorials/license-be-on-the-legal-side/),
[API documentation](https://openfoodfacts.github.io/documentation/).

## 4. Prices: freeze a reproducible catalog

For the first offline experiment, use fixed simulated prices in one currency,
explicitly marked in every product record and in the interface. Distinguish price
per purchasable pack from cost per gram or millilitre. Keep all methods on the same
price snapshot. This supports constraint experiments, not real-store savings claims.

Open Prices is an optional later source for observed prices. Its official docs
describe crowdsourced price observations with receipt or shelf-tag evidence and
provide API, JSONL exports, and a Hugging Face dataset. Use matching barcode,
currency, observation date, location, and relevant quantity/discount fields when
available. Price observations from different stores or dates do not establish one
simultaneously purchasable cart. Local coverage and exact product overlap remain unmeasured.
The project declares ODbL data terms.

Sources: [official price overview](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/tutorials/product-prices/),
[access and export documentation](https://github.com/openfoodfacts/open-prices/blob/main/docs/guides/data.md).

## 5. Alternatives considered

| Source | Why it is useful | Why it is not the default |
| --- | --- | --- |
| dunnhumby The Complete Journey | Provider describes two years of household transactions for 2,500 households. A related 84.51/completejourney release documents quantities, spend, and partial pack-size metadata. | Strong fallback if Instacart access fails or historical price analysis becomes central. Product descriptions can be coarse, dietary data is absent, and releases differ. Original dunnhumby and the package's 2,469-household/one-year release must not be conflated. |
| RecipeNLG | Established research dataset with 2,231,142 recipes and full ingredient text, often including units. | Published schema lacks an explicit servings field. It requires parsing and review, and its data terms restrict use to non-commercial research/education. It is not a turnkey quantity-aware recipe source. |
| USDA FoodData Central | Authoritative nutrient and food-description source; CC0, with downloads and an API. | Useful optional food/portion reference, but does not provide grocery purchase histories or store prices. Serving-size fields are not automatically package sizes or ingredient-specific density conversions. |

Sources: [dunnhumby provider](https://www.dunnhumby.com/source-files/),
[completejourney release description](https://github.com/bradleyboehmke/completejourney/blob/master/DESCRIPTION),
[product schema](https://bradleyboehmke.github.io/completejourney/reference/products.html),
[transaction schema](https://bradleyboehmke.github.io/completejourney/reference/transactions.html),
[RecipeNLG author repository](https://github.com/Glorf/recipenlg),
[RecipeNLG schema and terms](https://huggingface.co/datasets/mbien/recipe_nlg/blob/main/README.md),
[USDA guide](https://fdc.nal.usda.gov/api-guide/).

## 6. Data SmartCart still needs to create

- A reviewed canonical ingredient taxonomy and synonym mappings.
- Recipe-to-ingredient and product-to-ingredient mapping tables with evidence.
- A catalog with stable internal IDs, pack quantity/unit, price per pack, currency,
  availability policy, dietary evidence, source IDs, and synthetic flags per attribute.
- Intent/slot examples for budgets, servings, quantities, pantry stock, exclusions,
  revisions, and unsupported requests. Proposed full target: 900 examples, split
  600/150/150 by seed/template family, with independent review of at least 20%.
- Proposed retrieval benchmark: 50 development and 100 test queries.
- Proposed basket benchmark: 50 development scenarios plus 200 final scenarios
  (120 feasible, 40 infeasible, 40 clarification cases), independently labeled.
- Separate final request families from parser training and development. Maintain
  separate historical purchase-ranking and grocery-goal evaluation tracks.

These are project-specific annotations and curated data, not existing downloaded labels.

## Original acquisition plan

1. Obtain the required Instacart files through an accessible route and record the
   applicable terms, version, byte sizes, and checksums. If unavailable, inspect
   the exact Complete Journey release before choosing it as the fallback.
2. Save a pinned UniTools recipe snapshot with attribution and inspect five candidate
   recipes. Retain only records whose required amounts, units, servings, scaling,
   dietary assumptions, and ingredient mappings can be reviewed.
3. Define the catalog, recipe, mapping, and provenance columns; assemble 20 product
   options covering those recipes, with clearly marked fixed simulated prices.
4. Write a short audit showing missing units, vague quantities, duplicate IDs,
   unsupported ingredients, mapping coverage, and dietary unknowns.

Completion evidence: five accepted recipes, a covering 20-product pilot catalog,
traceable sources, and an audit with unresolved issues. Model training follows
only after this data path is coherent.

## Current direction after acquisition

Work with the supplied Instacart and Food.com files first. The audit measures
which Food.com records have aligned ingredient/quantity lists and usable servings,
but it does not resolve missing units. Review five recipe candidates against
recorded sources before creating quantity-aware recipe data. UniTools remains
an optional alternative if unit verification cannot be completed from Food.com;
it is not an additional dataset required for this stage.
