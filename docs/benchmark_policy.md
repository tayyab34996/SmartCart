# Benchmark policy (Phase 4, D2)

This document defines what the Phase 4 benchmarks mean. Every basket label comes from
`smartcart.validation.feasibility.check_feasibility`, which implements the model below.
Later phases (parsers, retrieval, the CP-SAT solver, the validator) must use the same
semantics, or their scores against these labels are not meaningful.

Files are built by `scripts/build_benchmarks.py` from `configs/benchmarks.json`.
Counts come from `results/metrics/benchmark_checks.json`. Hashes of the test files are in
[benchmark_lock.md](benchmark_lock.md).

## Supported basket model

- **Requirements:**
  - The recipe lines are scaled linearly to the requested servings. When no servings are
    given, the recipe's base servings are used (and the gold `servings` stays `null`).
  - Explicit `items` are added.
  - Amounts are aggregated per ingredient and unit.
- **Pantry:** amounts are in the requirement's unit (`g`, `ml` or `piece`) and are
  subtracted. A line fully covered by the pantry needs no purchase. A pantry amount of
  `null` means unknown, which triggers `missing_pantry_quantity`. Pantry keys that match
  no requirement are reported and otherwise ignored.
- **Exclusions:** an excluded ingredient is **dropped from the requirements** (the user
  cooks without it), and none of its products may be bought. Excluding an ingredient
  that the request does not use has no effect on cost.
- **Purchase:** each remaining line is bought as **one product type**, in the minimum
  number of whole packs. Mixing products for one line, and multi-ingredient bundles, are
  out of scope.
- **Eligibility:** a product is eligible when it has the same ingredient and unit, is
  available, and every requested diet is `"allowed"`. **`"unknown"` never satisfies a diet.**
- **Budget:** an inclusive cap in PKR minor units. No budget means no cost limit.
- **Label:**
  - `feasible` when every line has an eligible product and the minimum total cost is
    within the budget;
  - `infeasible` otherwise, with reason `no_eligible_option` (which reports the
    ingredient and the counts at each eligibility step) or `budget_below_minimum_cost`
    (which reports the required budget);
  - `clarification` when the gold request needs clarification;
  - `unsupported` for out-of-scope requests.
- **Minimum cost:** found by depth-first enumeration of every combination of eligible
  options. Pruning only removes branches whose lower bound already exceeds the best basket
  found. A test compares the pruned search with full enumeration.

## StructuredRequest additions

The contract in BUILD_PHASES section 4.3 is unchanged except for:

- **Clarification type `missing_item_quantity`:** a grocery-list item has no amount
  ("buy potatoes and milk").
- **Clarification type `low_confidence_intent`:** stays in the contract for runtime model
  confidence. It is never a gold label, because a gold annotation has no confidence.

| Clarification type | Gold trigger |
| --- | --- |
| `missing_recipe` | A meal request with no dish ("plan a vegetarian dinner"), or a dish the catalog does not have ("biryani", "sushi"). The prompt offers up to three supported recipes that are feasible under the request's diet, budget and servings. |
| `missing_budget` | Vague cost wording ("on a budget", "keep it cheap", "make it cheaper"). A request with no cost wording has no budget limit and needs no clarification. |
| `missing_pantry_quantity` | A pantry item with no amount ("I already have some flour"). |
| `missing_item_quantity` | A grocery-list item with no amount. |
| `ambiguous_diet` | Diet wording that maps to no supported rule ("healthy", "light", "low-carb", "keto", "clean"). |

## Annotation scheme (NLU)

- **Labels:** `MEAL`, `PRODUCT`, `BUDGET`, `CURRENCY`, `SERVINGS`, `QUANTITY`, `UNIT`,
  `DIET`, `EXCLUSION`, `PANTRY`, in BIO tags over the tokenizer in
  `smartcart.benchmarks.language.tokenize`.
- **Spans:** each span is stored with character offsets, the normalized value and, for
  `QUANTITY` and `UNIT`, `attach_to`, the index of the item span it belongs to. This is the
  quantity-attachment gold.
- **Negation:**
  - A negated *diet category* is one `DIET` span that includes the cue ("no dairy",
    "no meat").
  - A negated *ingredient* is an `EXCLUSION` span on the ingredient only ("no
    [cheddar]"), with the cue outside.
  - "Peanut butter" in a list is a `PRODUCT`; "no peanuts" is an `EXCLUSION` of `peanuts`.
- **Diet wording:** "lactose-free" is not dairy-free (lactose-free milk is dairy), so it is
  never annotated as `dairy_free`.
- **Budget wording:** "under X" and "below X" are treated as inclusive caps. They are never
  generated for scenarios whose budget equals the minimum cost (the designs `exact`,
  `one_short`, `pantry_full` and `list_exact`), so the wording cannot contradict the label.
- **Revisions:** each `revise_basket` example carries the previous gold request in
  `session`. Its gold is the merged request.

## How the data was produced

The 900 NLU examples and the 250 basket scenarios are **template-generated**, not written
by people. This is the main limitation of the benchmark, and the report must state it.

- A *spec* fixes the meaning of one request. Three paraphrases of each spec share a
  `seed_id` and the same gold request (apart from `request_id`).
- **Phrasing templates are partitioned by split**, so dev and test text uses templates
  never seen in training. Lexical items are shared vocabulary: ingredient aliases from
  `synonyms.csv`, recipe aliases from `data/processed/recipe_aliases.csv`, unit words and
  number words.
- Gold labels are written together with the text, so tags cannot drift from values. Tests
  check that BIO tags decode to the stored spans and that span values agree with the gold
  request.
- Randomness uses only `random.Random.random()`, seeded from a hash of the seed ID, so the
  output is reproducible across Python versions. `--check` rebuilds every file byte-for-byte.

## Splits and groups (`data/splits/benchmark_groups.json`)

- **Meal families** are assigned whole to one split: 16 recipes train, 8 dev and 18 test.
  Grocery-list families (fixed ingredient sets) are drawn from their split's recipe
  ingredients.
- **NLU:** 200 / 50 / 50 seeds (600 / 150 / 150 examples), split by `seed_id`. No family
  appears in two splits.
- **Baskets:** dev (50) uses dev families; test (200) uses test families. **No test family
  appears in dev or in NLU training.**
- **Retrieval:** ingredients are split 40 dev / 78 test. The 50 dev and 100 test queries
  target disjoint ingredients, so test ingredients are never tuned on.

## Basket scenarios

- **Test:** 120 feasible, 40 infeasible and 40 clarification scenarios across 24 families
  (18 recipes and 6 grocery lists). **Dev:** 30 / 10 / 10 across 12 families.
- **Designs:** each label category has designs, and every (family, design) pair is visited
  in a seeded order. Exact counts per design are in `benchmark_checks.json`.
  - Feasible: generous budget, no budget, exact budget, partial pantry, a pantry that
    covers a line (with the budget set to the post-pantry minimum), exclusion,
    out-of-recipe exclusion, compatible diet, multi-pack servings, and grocery lists.
  - Infeasible: budget below the minimum, budget one rupee short, and diet conflict (no
    eligible product for some line).
  - Clarification: the five types above.
- **Clarification scenarios** carry a `clarification_answer` and the `resolved_request`
  with its own checker label, for the three-turn clarification metric in Phase 11.
- **`has_history`:** 40 test and 10 dev scenarios have an Instacart `user_id` from the
  Phase 3 sample. The user's Track B training orders contain at least two of the
  scenario's required ingredients, via the reviewed ingredient mapping. History never
  changes a label.

## Retrieval queries

- **Source:** 150 hand-written queries in `configs/retrieval_queries.csv`, of these types:
  synonym, brand (real brand names as noise), misspelling, Urdu transliteration,
  misleading near-match, and diet-constrained.
- **Relevant set:** every available catalog product of the target ingredient, restricted to
  products that are `"allowed"` for the query's dietary rules when it has any.
  Relevance is at ingredient level, because catalog products are simulated house brands.

## Known limitations

- **Synthetic language.** The text is template-generated. Real requests are messier, so
  parser scores here are likely optimistic. The held-out templates reduce, but do not
  remove, this bias.
- **Review.** The annotation review was done by the build agent, which also wrote the
  generator. See [annotation_review.md](annotation_review.md); an independent
  second-person check is still pending.
- **Grammar.** Number agreement on ingredient nouns is not inflected ("one corn tortillas",
  "six egg"). Gold labels are unaffected.
- **Recipes** are US-centric Food.com recipes (see the data card). The PKR prices are simulated.
