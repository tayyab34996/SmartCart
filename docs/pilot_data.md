# Pilot data contracts and examples

The first seed dataset contains **3 source-checked recipes, 11 canonical
ingredients, and 20 simulated product options**. It is for development and
quantity/cost checks, not a final test benchmark or a live store catalog.
The five-recipe milestone is not complete. No basket selector or request parser
is implemented in this stage.

The seed is [catalog.json](../data/processed/pilot/catalog.json). The executable
contract is [contracts.py](../src/smartcart/data/contracts.py); it uses the Python
standard library. Required fields are exact: missing fields and unexpected
fields are rejected to expose misspelled column names.

## Schemas

| Record | Required fields | Rules |
| --- | --- | --- |
| Dataset | `schema_version`, `purpose`, `currency`, `minor_units_per_major`, `sources`, `ingredients`, `conversions`, `products`, `recipes` | Version 1, offline simulation, PKR, 100 minor units per PKR. Collections must be nonempty with unique IDs. |
| Source | `id`, `title`, `locator`, `kind`, `checked_on`, `notes` | Recipe page, metrology reference, ingredient reference, or design policy. Every evidence reference must resolve. |
| Ingredient | `id`, `name`, `aliases`, `supported_units`, `mapping_status` | Reviewed seed mapping; unambiguous aliases; supported units drawn from `g`, `ml`, `piece`. |
| Conversion | `id`, `from_unit`, `to_unit`, `factor`, `ingredient_id`, `kind`, `evidence_ids` | Positive decimal-string factor; ingredient-specific estimates and package definitions must name their ingredient. |
| Product | `id`, `name`, `ingredient_id`, `pack_amount`, `pack_unit`, `price_minor`, `currency`, `available`, `dietary`, `attribute_source_id`, `simulated_fields`, `external_ids` | Positive pack size; whole pieces in count-based packs; integer nonnegative pack price; explicit simulation provenance; no external SKU matches in this seed. |
| Recipe | `id`, `name`, `source_recipe_id`, `source_id`, `base_servings`, `review`, `scaling_policy`, `scope_notes`, `ingredients` | Positive integer base servings, recorded source check, supported scaling policy, and a purchasable option in the correct unit for each ingredient. |
| Recipe line | `ingredient_id`, `source_ingredient`, `source_amount`, `source_unit`, `conversion_id`, `amount`, `unit` | Source amount retained as a fraction string; normalized positive decimal-string amount must match its conversion. |
| Recipe review | `status`, `reviewer`, `checked_on`, `independent_review_status` | Current status is `source_checked`, reviewer is `codex_source_check`, and independent review is `pending`. This does not claim a second human review. |

Dietary attributes are `vegetarian`, `vegan`, `gluten_free`, `dairy_free`, and
`nut_free`. Each is `allowed`, `disallowed`, or `unknown`. All current product
values are **unknown**; they cannot satisfy hard dietary requirements without
additional evidence. Ingredient names alone are not verified product labels.

All amounts are strings to avoid binary floating-point artifacts. Prices are
integers in minor units: `45000` means a **simulated PKR 450 per pack**, not a price
per gram. A product is exactly one ingredient option in this core model.

## Source checks and normalization

| Recipe | Base servings | Evidence and scope |
| --- | ---: | --- |
| Chicken Quesadillas — 3978 | 10 | [Original ingredient list](https://www.food.com/recipe/chicken-quesadillas-3978): weight-based chicken and cheese, one 16-ounce salsa jar, and ten 8-inch tortillas. Optional sides and dips are excluded. |
| Homemade Pasta — 3474 | 4 | [Original ingredient list](https://www.food.com/recipe/homemade-pasta-3474): flour, eggs, oil, water. This produces pasta dough, not a complete dinner. |
| Honey Lime Chicken — 19090 | 4 | [Original page Recipe JSON-LD](https://www.food.com/recipe/honey-lime-chicken-19090): honey, soy sauce, lime juice, and four chicken breasts. Piece counts remain piece counts. |

Review date: 20 October 2026. These records were checked against source pages by
the coding assistant. They are not culinary trials, medical/dietary validation,
or independently reviewed final benchmark labels. The original audit's 50-record
shortlist stays unchanged; the three source checks are recorded in this separate seed.

Food.com's US volume measures are interpreted as US customary measures under
an explicit planning policy. The factors `236.5882 ml/cup`, `14.78676 ml/tablespoon`,
and `453.59237 g/pound` follow [NIST SP 811](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b9).
The salsa package is treated as 16 avoirdupois ounces, or one pound, as specified
in its recipe; this is not a fluid-ounce conversion.

Flour uses the [King Arthur reference of 120 g per cup](https://www.kingarthurbaking.com/learn/ingredient-weight-chart).
That is a documented ingredient-specific planning estimate, not the measured
density of the source recipe's flour. Its use is recorded on the conversion and
in the recipe scope notes. It must never be applied to another ingredient.

Scale the **original source amount** by requested/base servings, apply the named
conversion, and round up once to 0.001 base units. Do not repeatedly scale already
rounded quantities. This rounding policy is deterministic and does not turn
reference coefficients into exact physical measurements.

Mass, volume, and count stay separate. The same chicken ingredient supports both
grams and pieces, but a gram-based product cannot cover a piece-based requirement.
No gram weight is assigned to a chicken breast or egg. Whole-pack purchasing
and pantry subtraction belong to the next basket implementation.

## Simulation policy

- Every product ID and name identifies a designed example, with no real brand or
  store association. The tortilla examples represent the source's 8-inch type.
- Pack sizes, prices, availability, and dietary state fields are explicitly listed
  in `simulated_fields` and attributed to `simulation_v1`.
- Prices are fixed development inputs, not observed Pakistani retail prices or
  evidence of savings. Availability is simulated, not live inventory.
- `external_ids` is empty. No match to an Instacart product or Open Food Facts
  barcode has been verified. Those joins must be reviewed separately later.
- Water is a required, purchasable ingredient in the pasta example unless a future
  request explicitly supplies enough pantry water. It is not silently assumed free.
- The seed contains limited factual ingredient/quantity references and source
  attribution, not copied cooking instructions, images, or raw transaction records.

## Run and inspect

```powershell
python scripts/validate_pilot.py
python scripts/validate_pilot.py --recipe foodcom_3474 --servings 2
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

For two pasta servings, the documented planning requirements are 120 g flour,
one egg, 7.394 ml oil, and 29.574 ml water. The command calculates ingredients;
it does not yet choose packs, enforce a budget, or build a basket.

The three product-backed recipes cover all twelve recipe lines. The current
approval means the seed satisfies its development contract, not that every
upstream recipe, dietary claim, or final experiment is validated.

## Deferred source issue

[White Lightning Chili — 46421](https://www.food.com/recipe/white-lightning-chili-46421)
describes a large jar of beans alongside wording that identifies dry beans and
says not to drain them. This is unresolved preparation-state evidence. It was
not admitted by silently replacing dry beans with cooked beans.

## Next task

Build the simple structured-request basket baseline over this seed: scale servings,
subtract explicit pantry quantities, choose whole packs, calculate total cost,
and independently check coverage and budget. Add two more source-checked meal
recipes to reach the original five-recipe milestone before expanding the benchmark.
