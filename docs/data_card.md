# SmartCart data card — full catalog (D2, Phase 2)

Built 2026-11-25 by `scripts/prepare_data.py` from reviewed inputs. Generated checks are in
`results/metrics/catalog_checks.json`, and `--check` verifies the committed catalog
rebuilds identically.

## Summary

| Item | Value |
| --- | --- |
| Recipes | 42 (3 pilot + 39 new) from Food.com, across 27 meal families |
| Recipe lines | 274, all mapped to a canonical ingredient and covered by an available product |
| Ingredients | 118: 98 used in recipes, plus 20 distractors used only for retrieval near-misses |
| Aliases (synonyms) | 167, in `data/processed/synonyms.csv` |
| Products | 466 simulated product options; 4 deliberately unavailable |
| Currency | PKR, integer minor units (100 paisa per rupee) |
| Units | `g`, `ml`, `piece` |
| Schema | Same as the pilot plus `meal_family`; validated by `validate_catalog()` |

## Files

| File | Role |
| --- | --- |
| `data/processed/recipes.csv` | Recipe metadata: ID, name, meal family, servings, page URL, scope notes |
| `data/processed/recipe_lines.csv` | One reviewed row per ingredient line: verbatim page text, amount, unit, conversion, resolution note |
| `data/processed/ingredients.csv` | Canonical ingredients: role, category, pack sizes, simulated price per unit, dietary labels |
| `data/processed/synonyms.csv` | Reviewed aliases, with origin `pilot`, `recipe_page`, `common_name` or `common_name_transliteration` |
| `configs/catalog_build.json` | Sources, conversions, brands, price policy, dietary variants, targets |
| `data/processed/catalog.json` | Generated output (do not edit by hand) |
| `data/processed/pilot/catalog.json` | Frozen pilot (20 products, 3 recipes); every pilot record is carried into the full catalog unchanged |

## Sources and terms

- **Food.com Recipes and Reviews** (Kaggle, irkaal), in `data/raw/archive_4.zip`.
  - Used for recipe selection, recipe IDs and **servings** (`RecipeServings`).
  - The dataset has quantities but **no units**, and its quantity lists are misaligned
    for recipes with "X or Y" alternatives (for example 83561 and 115954).
  - Units and quantities therefore come from each recipe's **food.com page**, fetched
    2026-11-25 and recorded per recipe as a `recipe_page` source.
  - Recipe text belongs to its authors and is used here for non-commercial coursework only.
- **Instacart Market Basket Analysis** (Kaggle competition data), in `data/raw/archive_3.zip`.
  Not used in Phase 2. Phase 3 uses it for transactions.
- **NIST SP 811:** lb, oz, cup, tbsp and tsp conversion factors.
- **King Arthur Baking ingredient weight chart:** cup-to-gram reference estimates for the
  ingredients listed in `configs/catalog_build.json`. These are not measured densities.

Raw archives are not redistributed. See `data/README.md` for acquisition and
`docs/data_audit.md` for the archive hashes.

## Recipe selection

1. Start from 522,517 Food.com recipes.
2. Keep recipes with equal-length quantity and ingredient lists, no missing quantities,
   4–9 ingredients (up to 11 for stews), at least 15 reviews (8 for stews), and servings
   of 2–8. This leaves 709.
3. Remove recipes containing pork or alcohol. This is a **design choice** for the
   PKR / Pakistan simulation context, and it is reversible.
4. Keep savory main dishes and sides (no desserts, drinks, breads or sauces) and assign
   each recipe one meal family by name.
5. Pick the most-reviewed candidates across families. 51 pages were checked:
   **39 accepted, 12 rejected**, plus the 3 pilot recipes.

**Rejected,** because a line could not be converted without inventing a number:

| Recipe | Reason |
| --- | --- |
| 22910 Quick Chinese Fried Rice | Instant rice has no cited weight |
| 116029 Tofu and Broccoli Stir-fry | Cups of chopped broccoli |
| 53508 Chicken Salad With Grapes | Cooked chicken, celery and grapes by volume |
| 11508 Tuna Melt | Celery by volume |
| 21855 Indian Spiced Rice | Sliced green onion by volume |
| 43737 Grilled Lime Shrimp | Lime zest by volume |
| 16666 Lentils, Garlic and Tomatoes | Dry lentils by volume |
| 191459 Easy Lentil Stew | Chopped potato and carrot by volume |
| 346135 Beef Stew for Two | Chopped potato and carrot by volume |
| 123588 White Pizza | The page lists toppings only, no crust; sliced onion by volume |
| 83203 Korean Roast Chicken Thighs | Minced green onion by volume |
| 65469 Garlic Roasted Potatoes | "1 head garlic" with an unknown clove count |

Consequences:

- There is no stew or stir-fry family.
- Recipes are US-centric; the transliterated aliases partly compensate on the request side.
- Several recipes are sides rather than full dinners (`vegetable_side`, `rice`). Their
  meal family says so.

## Recipe line resolution policy

The plan says to "reject or manually resolve vague quantities; do not invent missing
amounts." Every manual resolution is recorded in the `resolution` column of
`recipe_lines.csv` and counted in `catalog_checks.json`:

| Rule | Lines | Rationale |
| --- | --- | --- |
| As published | 220 | — |
| Range ("6-8", "1/2 - 1") → upper bound | 5 | Guarantees coverage |
| "X or Y" → first option | 7 | Deterministic |
| Lines marked optional → excluded | 1 (red pepper flakes) | — |
| dash = 1/8 tsp, pinch = 1/16 tsp | 8 | Project convention, not a standard |
| "1 bunch green onion" = the catalog bunch of 6 stalks | 1 | Catalog packaging definition |
| Cans and fillets "2 (8 ounce)" → multiplied out | 3 | Stated net mass |
| Flour assumed all-purpose; cheese assumed shredded; herbs assumed dried | 10 | Stated per line |
| Weight-chart row reused for a close form (chopped vs diced onion, basmati vs long-grain, packed brown sugar) | 4 | Closest cited row |
| Variant mapped to the general ingredient (fat-free mayonnaise, nonfat yogurt) | 2 | — |

**Unit choices:**

- Spices, dried herbs, salt, seasonings, condiments, purées (salsa, applesauce, ricotta)
  and chopped fresh herbs are measured and stocked **by volume (ml)**. This is a
  simulation simplification; real stores sell many of these by weight.
- Garlic `piece` means one clove (a bulb pack is 10 cloves).
- Cilantro `piece` means one bunch.
- Green onion `piece` means one stalk.

## Simulation policy

**Every product attribute is simulated**, and each product declares it in
`simulated_fields`. That covers the name, pack amount and unit, price, currency,
availability and dietary values. Names start with `SIMULATED`.

- **House brands are fictional:** SmartCart Basics, SmartCart Select and SmartCart
  Organic. No real brand, store price or Instacart SKU is claimed, and every
  `external_ids` is `{}`.
- **Products per ingredient:**
  - one Basics product for each pack size;
  - one Select product (largest pack, ×1.18 price);
  - one Organic product (smallest pack, ×1.40) for produce, dairy, egg and grain;
  - dietary variants where configured.
- **Prices:** a per-ingredient PKR base price per unit × pack size × a size discount
  (1.00 / 0.93 / 0.87 / 0.82) × the brand factor, rounded to whole rupees. Prices are
  plausible-looking but invented. They support comparing methods offline, **not claims
  about real savings**.
- **Availability:** Basics products are always available. A deterministic hash marks
  about 1 in 29 of the other products unavailable (4 products), so availability
  handling gets tested.
- **Pilot products** (20) keep their original values, including all-`unknown` dietary
  labels.

## Dietary policy

Each product has `allowed`, `disallowed` or `unknown` for `vegetarian`, `vegan`,
`gluten_free`, `dairy_free` and `nut_free`.

- Labels are **designed** from general ingredient knowledge. They are not read from
  product labels.
- `unknown` is used where real products vary: blends such as curry powder or cajun
  seasoning; processed sauces; cheeses that may use animal rennet (cheddar, Jack,
  ricotta, cream cheese); oats (cross-contamination).
- Clear cases are set explicitly:
  - Parmesan is not vegetarian (traditional animal rennet).
  - Worcestershire sauce is not vegetarian (anchovy).
  - Soy sauce contains wheat.
  - Peanuts and peanut butter are not nut-free.
- **Dietary variants** give hard diet requests feasible options: vegetarian cheddar,
  Jack and hard cheese; gluten-free tamari, pasta and breadcrumbs; vegan mayonnaise and
  plant-based butter; anchovy-free Worcestershire; vegetarian bouillon; gluten-free
  seasoning salt.
- **For a hard dietary request, `unknown` never counts as satisfying it.**

## Known gaps and limitations

- **Independent review is pending for all 42 recipes** (`independent_review_status:
  pending`). Lines were checked by the build agent against fetched page text, not
  against rendered HTML.
- Ingredient mappings for new ingredients are `agent_reviewed`, not independently reviewed.
- Servings come from the dataset because the fetched page text showed no servings value.
- Weight-chart conversions are reference estimates. Chopped vegetables measured by
  volume are unsupported, which is why some recipes were rejected.
- No Instacart product IDs are attached to catalog products. Ingredient-level mapping
  to Instacart is Phase 3.
- `filter_eligible_candidates()` in `src/smartcart/retrieval/filtering.py` checks
  dietary values with `is True`, but the catalog contract uses `"allowed"`. As written,
  no product can pass a dietary filter. To be fixed in Phase 7.
