# Source data dictionary

These fields describe the downloaded CSVs. They are not yet SmartCart's normalized
catalog or recipe schema. See [the measured audit](data_audit.md) for row counts
and [the data guide](../data/README.md) for local paths.

## Instacart

| File | Key and relationships | Fields used initially |
| --- | --- | --- |
| `aisles.csv` | Primary key: `aisle_id` | `aisle`: category name. |
| `departments.csv` | Primary key: `department_id` | `department`: category name. |
| `products.csv` | Primary key: `product_id`; foreign keys: `aisle_id`, `department_id` | `product_name`: source product text for mapping and retrieval. |
| `orders.csv` | Primary key: `order_id`; grouped by `user_id`; sequence given by `order_number` | `eval_set`, `order_dow`, `order_hour_of_day`, `days_since_prior_order`. |
| `order_products__prior.csv` | Order/product pair; joins to `orders` and `products` | `add_to_cart_order`, `reordered`. |
| `order_products__train.csv` | Same relationship as prior lines, for labeled final training orders in the source competition | `add_to_cart_order`, `reordered`. |

`eval_set` is the source competition label. SmartCart will create its own
chronological training/validation/test manifests from labeled purchase histories.
An order marked source `test` does not supply known purchased-item labels for
our local ranking evaluation.

Important meanings:

- `add_to_cart_order` is a position, not a quantity.
- `reordered` is a source binary flag, not a quantity or current preference label.
- A missing inter-order gap on an initial order is expected.
- No actual calendar date is supplied for these orders.
- Product names and categories do not establish a pack size, price, allergen
  status, or equivalence to an external product.
- IDs are source-local. A Food.com recipe ID or external barcode with the same
  numeric value is unrelated.

## Food.com recipes

| Field | Meaning and initial handling |
| --- | --- |
| `RecipeId` | Source recipe identifier; retain for traceability. |
| `Name` | Recipe title; use for discovery and human review. |
| `RecipeCategory` | Source category; useful for profiling, not verified meal or diet suitability. |
| `RecipeIngredientParts` | R-style list string in the CSV containing ingredient names; parse without execution. |
| `RecipeIngredientQuantities` | R-style list string of source amounts; can contain missing entries and unequal list lengths. Units are not independently established. |
| `RecipeServings` | Source servings value; require a finite positive number and human review for admitted recipes. |
| `RecipeYield` | Free-text yield; do not silently substitute it for servings. |
| `RecipeInstructions` | Source instructions; potentially useful during review, not assumed to resolve all missing units. |
| `Keywords` | Source tags; discovery hints rather than hard dietary proof. |
| `CookTime`, `PrepTime`, `TotalTime` | Source duration text; not required for the first basket calculation. |
| Nutrition fields | Source values; not validated or used as hard nutrition constraints in this stage. |
| Author, review, rating, image, and publication fields | Present in the source; not needed for the first recipe-to-basket pilot. |

There is no dedicated ingredient-unit column in the inspected CSV header.
The Parquet copy is an alternative representation of the source, not assumed to
repair missing ingredient units. It has not been scanned in the initial audit.

## Required review before normalization

For each accepted recipe, record its source identifier, base servings, canonical
ingredient IDs, explicit amount and unit per required ingredient, evidence for
any correction, reviewer, and review status. Reject unresolved list alignment or
quantities. A quantity inferred by a model is not a verified source fact.

For each catalog option, separately record product identity, canonical ingredient,
pack amount/unit, price per pack, currency, availability policy, and dietary
evidence. Mark every simulated attribute explicitly. Pantry quantities must use
compatible dimensions before subtraction.

Keep grams, millilitres, and pieces separate. A general millilitre-to-gram
conversion is invalid; an ingredient-specific documented conversion is required.

Next task: use the audit's shortlist to complete these reviews for five recipes,
then create their ingredient mappings and a covering 20-option catalog.
