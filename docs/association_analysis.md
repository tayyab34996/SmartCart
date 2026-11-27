# Association analysis and Track B (Phase 8)

All numbers come from files written by committed code:
- `results/metrics/association_rules.json`: the mined rules;
- `results/metrics/trackb_validation.json`: the Track B results;
- `results/metrics/association_selection_activity.json`: whether the terms change selection.

They are made by `scripts/mine_rules.py` and `scripts/evaluate_trackb.py` with the frozen
`configs/associations.json`. The Track B **test** orders (each user's final order) were not
read; they are evaluated once in Phase 11.

## Setup

- **Ingredient level.** No catalog product has a verified Instacart ID (catalog products
  are simulated), so every order is reduced to the set of catalog ingredients its
  products map to (Phase 3 mapping, 89.3% held-out precision).
  - 119,846 of the 163,626 training orders (73%) contain at least one mapped ingredient.
  - 117 of the 118 catalog ingredients occur.
- **Training orders only.** Rules are mined with FP-Growth (`mlxtend`, `max_len=3`) on the
  Track B training orders of the 10,000 sampled users. Orders without a mapped ingredient
  stay in the support denominator. A test checks every exported pair count against the
  training orders, and that adding the validation orders would change it.
- **Memory profile** (`results/metrics/association_mining_profile.json`, machine-dependent):
  pairs and then `max_len=3` at a minimum count of 10.
  - 21,247 itemsets and 112,692 rules.
  - 6.5 s and a peak RSS of 295 MB on the team's Windows machine, so memory was never a
    constraint.
- **Pair score:** `1 − 1/lift` for a pair that passes the thresholds and has lift > 1,
  else 0. It is symmetric and lies in [0, 1].
  `smartcart.associations.api.basket_pair_score` averages it over pairs, so an objective
  never sums an unbounded number of scores.
- **History score:** the share of the user's training orders that contain the ingredient.
- **Thresholds and weight** were tuned on half of the validation users ("tune") by the
  rule in the config, written before any result existed, and reported on the other half
  ("report").
  - Grid: minimum count {10, 25, 50, 100, 200} × minimum confidence {0, 0.05, 0.1, 0.2}
    × weight {0.1, 0.25, 0.5, 1, 2}.
  - Selected: **count ≥ 200, confidence ≥ 0.2, weight 0.1**.
  - This leaves 138 ingredient pairs with a positive score. `data/processed/rules.csv`
    has 777 rules: 280 directional pair rules and 497 triples.

## Descriptive view

Figure `12_association_rules.png`:
- **Left:** the most frequent ingredients. Milk is in 22.6% of training orders, then egg,
  onion and almond milk.
- **Right:** the strongest pairs by lift.

The data are US Instacart baskets. Almond milk is genuinely one of the most bought items
(about 10% of training orders); the products mapped to it are almond-milk products, so
this is not a mapping error. Associations learnt here describe US shopping, not the PKR context of the simulated
catalog.

## Strongest rules, read by hand

The build agent read the top 20 pairs by lift and by count and the top triples. This
review is not independent.

**Plausible complements (helpful):**
- **cilantro + lime:** count 1,588, lift 6.1. It extends to triples such as
  {black beans, lime} → cilantro (lift 11.2) and {garlic, lime} → cilantro.
- **garlic + onion** (3,349, lift 3.9), **onion + tomato paste**, **garlic + tomato paste**,
  **green bell pepper + onion**, **canned diced tomatoes + onion**: cooking bases.
- **butter + white flour** (lift 4.5), **butter + sugar**, **brown sugar + butter**,
  **butter + heavy cream**: baking.
- **mozzarella + ricotta** (6.8) and **parmesan + ricotta** (6.5): lasagne-style dishes.

**Misleading or of limited use:**
- **black beans + pinto beans** (the strongest pair, lift 10.4) and **beef broth + chicken
  broth** (7.2) are near-substitutes bought together when stocking up. A recipe rarely
  needs both, so a "goes well with" bonus between them would be wrong for basket building.
- **Pairs ranked by count are dominated by popularity.** milk + egg (6,167 orders), milk +
  onion and almond milk + milk all have lift ≤ 1.6. The lift-based score correctly gives
  them little weight. Two pairs pass the thresholds with lift ≤ 1 and score 0.
- **Mapping errors propagate.** About 1 in 10 mapped products is mapped to the wrong
  ingredient (Phase 3), so some co-occurrences are artefacts of the mapping rather than
  of shopping.

## Track B (validation orders)

Figure `13_trackb_validation.png`. The target is each user's validation order as a set of
ingredients. Of the 10,000 users, 2,661 are excluded because their validation order has no
mapped ingredient (recall is undefined), leaving 7,339: 3,669 tune and 3,670 report. All
rankers rank the same 118 ingredients and return 10 each. Ties go to popularity, then to
the ingredient ID.

**Report half (3,670 users):**

| Ranker | Recall@10 | NDCG@10 | Repeat items R@10 / NDCG (3,215 users) | New items R@10 / NDCG (1,695 users) |
| --- | --- | --- | --- | --- |
| Popularity | 0.498 | 0.363 | 0.572 / 0.403 | **0.270 / 0.150** |
| Personal frequency [S9] | **0.701** | **0.584** | **0.906 / 0.731** | 0.122 / 0.049 |
| Frequency + association | 0.684 | 0.573 | 0.898 / 0.724 | 0.089 / 0.036 |

**Paired bootstrap** (2,000 resamples over report-half users, 95% percentile intervals):

| Comparison | NDCG@10 | Recall@10 |
| --- | --- | --- |
| Association − frequency | −0.010 [−0.013, −0.008] | −0.017 [−0.022, −0.012] |
| Frequency − popularity | +0.221 [+0.211, +0.231] | +0.203 [+0.191, +0.215] |

**Findings**

- **Personal frequency is a strong baseline**, as reported in [S9]: it beats popularity by
  about 0.22 NDCG@10 and finds 91% of repeat items in the top 10.
- **The association term makes ranking worse, not better.**
  - All 100 grid settings score below plain frequency on the tune half. The best reaches
    NDCG@10 0.577, against 0.586 for frequency.
  - The selection rule therefore chose the mildest setting in the grid (strictest
    thresholds, smallest weight).
  - The loss holds on the report half, and its interval excludes zero. This is a null
    (negative) result and is reported as such.
- **Why** (counts in `association_vs_frequency_report_half` of the metrics file): most of
  a user's list beyond their history is filled by popularity, and that
  fill is what finds new items. Even at weight 0.1 the association term reorders the fill
  for 3,405 of 3,670 report users.
  - It promotes niche complements of the user's history: heavy cream (663 lists),
    white flour, buttermilk, ricotta, rolled oats.
  - It pushes out popular staples: almond milk (909 lists), cucumber, egg, butter.
  - Popular staples are the better guess for a next basket. 130 report users gain a hit,
    262 lose one, and 3,278 are unchanged.
  - The term even hurts *new* items (Recall@10 0.089 vs 0.122), which is where an
    association signal would be expected to help.
- These are validation results on ingredient-level baskets. The Track B test comparison
  (Phase 11) uses the same frozen setting.

## Is the association score active in basket selection?

**No.** On the 50 dev basket scenarios (`association_selection_activity.json`):

- **The pair term is non-zero in 22 of the 49 scenarios with two or more lines, but never
  changes with the product chosen (0 of 49).** The selector picks one product per line,
  and the lines are fixed by the request. With ingredient-level rules every product of an
  ingredient has the same pair score, so the term adds the same constant to every
  candidate basket.
- **The history term is non-zero for 9 of the 10 users with history, but never changes
  with the product chosen (0 of 10)**, for the same reason.
- A test confirms that the measurement would detect a product-level score: a synthetic
  score that favours one house brand is flagged.

**Consequences for later phases**

- In Phase 9, the association and history terms can be computed and logged, but they
  cannot change which products are bought.
- E4 (E3 + association-aware scoring) will therefore select the same baskets as E3, and
  A3 (E4 with association weight 0) the same as E4. Phase 11 should report this as an
  analysis result rather than a model difference.
- The terms could matter only if they changed **which ingredients** are bought, for
  example when suggesting extra items for a grocery list. That is outside the current
  basket model (one product per required line).

## Limitations

- Ingredient-level aggregation through a mapping with about 89% precision; only 21% of
  sampled item rows map to a catalog ingredient.
- US Instacart behaviour, applied to a simulated PKR catalog.
- The rule review above was done by the build agent, not by an independent reviewer.
- The tune and report halves come from the same validation orders, so the report-half
  numbers are a held-out estimate within validation, not a test result.
