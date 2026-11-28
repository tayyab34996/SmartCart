# Failure analysis (Phase 11, test split)

Every case below comes from the committed test-split rows in
`results/predictions/runs/` (one row per scenario, run, mode and seed) or from
`results/metrics/test_components.json`. These files were made by `scripts/evaluate_all.py`
with the frozen configs, in the single test run on 2026-11-28. Scenario texts are quoted
from the locked `data/benchmarks/basket_test.json`.

The analysis was written **after** the test run and changes nothing in the system. It
explains the results; it was not used to tune anything.

## Where the failures are

| Run, mode | Failures (of 200) | Main causes |
| --- | --- | --- |
| E0, gold input | 18 | All 18 are diet scenarios: the post-hoc filter rejects a basket because the cheapest product in the pool is `unknown` for the diet (cases 1–2) |
| E3/E4, gold input | 0 | — |
| E4, end to end (3 seeds) | 36, 36, 32 | 22 scenarios fail in all 3 seeds, 30 more in 1–2. Causes: the dish not tagged after "We're having" (cases 3–4); a number attached to the wrong slot across a comma (5–6); an exclusion read as a pantry item (7–8); a diet phrase missed (9–10) |
| A1, end to end | 8 | The baseline parser's own errors (cases 11–14) |

For E4, the 36 failures of seed 42 break down as follows:
- 22 unnecessary questions: 17 "which dish?", 3 pantry quantity, 2 diet (6 of the 22 are
  on infeasible scenarios, so the infeasibility is never shown);
- 5 false rejections caused by a misread budget or servings;
- 4 baskets labelled valid that violate the user's actual request;
- 2 questions about the dish that were never resolved;
- 3 scenarios that needed a question but got a basket without one.

## Cases

**1. E0 rejects feasible diet baskets (selector failure, fixed by E3).**
- *Scenario:* `test_b025`, "Sort out the groceries for nut free baked oatmeal, three of us
  are eating, cap it at rupees 1,400/-".
- *What happened:* with the gold request, E0 picks the cheapest product per line and then
  filters. A cheapest product labelled `unknown` for nut-free is dropped, and the line is
  left `incomplete`. E3 applies the diet before choosing and buys a valid basket for
  PKR 1,250.
- *Scale:* all 18 of E0's gold-input failures have this cause: 8 feasible `diet_ok`
  scenarios, and 6 `ambiguous_diet` and 4 `broad` clarification scenarios whose answer
  adds a diet. This is the
  E3 − E2 difference of +0.090 [+0.064, +0.117], exactly as Phase 5 predicted.

**2. Retrieval quality does not change the E0 failures (E2 = E1).**
- *What happened:* moving E0's selector from TF-IDF top 10 to MiniLM top 40 changes no
  scenario outcome in either mode (E2 − E1 = 0).
- *Why:* every pool already contains each ingredient's cheapest product, because the
  queries are canonical ingredient names. The failure is the post-hoc filter, not the
  pool. Retrieval quality matters for free-text queries (component result: MiniLM
  Recall@10 0.764 vs TF-IDF 0.610), not for pipeline selection.

**3. DistilBERT misses the dish after "We're having" (parser span miss, held-out template).**
- *Scenario:* `test_b016`, "We're having green beans with garlic. cap it at 1,500 rupees,
  6 of us are eating".
- *What happened:* no RECIPE span is tagged, so the parser asks "Which dish?" although the
  dish is named. A1 (the baseline dictionary) finds it.
- *Scale:* across the 3 seeds, DistilBERT misses the dish in 29 of 123 "We're having"
  cases (24%), against 6–8 per template for the other three templates (at most 6%). The
  phrase opens 43 of the 200 basket-test requests and appears in none of the 600 NLU
  training texts.

**4. The same miss without a budget.**
- *Scenario:* `test_b017`, "We're having roast fillet of beef. 6 of us are eating". The
  dish alias is also unseen in training.
- *Pattern:* 17 of seed 42's 36 failures are unnecessary "which dish?" questions; 10 of
  those 17 requests start with "We're having". Over the 3 seeds DistilBERT finds the dish
  in 148–152 of the 167 scenarios that name one; the baseline's dictionary finds 164.

**5. A number crosses a clause boundary: "for a family of 4, 743 is my limit"
(attachment error; false rejection).**
- *Scenario:* `test_b007`, "Sort out the groceries for green beans with garlic. for a
  family of 4, 743 is my limit".
- *What happened:* DistilBERT reads the budget as "4" (PKR 4.00) and leaves servings unset.
  CP-SAT then correctly proves no basket fits PKR 4, which counts as a false rejection.
  It fails in all 3 seeds. Phase 6 saw the same pattern on a hand-written probe ("for 2
  under 1500 rupees").

**6. The same attachment error with "rupees".**
- *Scenario:* `test_b087`, "I'd like to prepare roasted brussels sprouts and for a family
  of 8, 2750 rupees is my limit".
- *What happened:* the budget becomes PKR 8.00, in all 3 seeds.
- *Scale:* per seed, DistilBERT gets the budget exact in 169–170 of the 175 scenarios
  with a budget, and the servings in 131 of the 139 dish scenarios with servings. The
  baseline gets 175/175 and 138/139. Neither "for a family of" (56 basket-test requests)
  nor "is my limit" (55) appears in the training texts.

**7. An exclusion read as a pantry item ("I don't want any tomato salsa").**
- *Scenario:* `test_b051`.
- *What happened:* DistilBERT tags "tomato salsa" as a pantry item with an unknown amount.
  It asks how much salsa the user has instead of leaving it out. This fails in all 3
  seeds; the phrase "I don't want any" never appears in training.

**8. The same with a transliterated alias ("I'm avoiding kali mirch").**
- *Scenario:* `test_b056`.
- *What happened:* "kali mirch" (black pepper) is mapped correctly, but read as a pantry
  item rather than an exclusion in 2 of 3 seeds; in the third the exclusion is dropped.
  "I'm avoiding" appears 13 times in the basket test and never in training; "I don't want
  any" appears 7 times, also never in training.

**9. A missed diet phrase produces a basket that is wrong for the user ("no meat") —
the most serious kind.**
- *Scenario:* `test_b072`, "Sort out the groceries for scrambled eggs, no meat and 950
  rupees is my limit".
- *What happened:* DistilBERT (seed 42) drops the diet. The selector correctly builds and
  validates a basket for the request *as parsed*, but against the user's actual request
  it breaks the vegetarian rule. This is a **violation among outputs labelled valid**.
  The selector and validator did their job; the error entered at parsing.
- *Scale:* there are 2–4 such outputs per transformer seed and none for the baseline
  parser. With gold input, no run produces one.

**10. Servings missed, so too little is bought, still labelled valid.**
- *Scenario:* `test_b002`, "Put together a basket for garlic chicken. for a family of six
  and 150 gm of bread crumbs is already in the kitchen, spending at most 3750 rupees".
- *What happened:* servings are not extracted, so the recipe's default servings are used.
  The basket is valid for the parsed request but has `insufficient_quantity` against the
  real one, in all 3 seeds.

**11. A baseline pantry rule swallows the dish (A1, `invalid_request`).**
- *Scenario:* `test_b011`, "We're having caramelized chicken wings and 1350 is my limit,
  I still have 2 kilograms of chicken wings".
- *What happened:* the baseline treats the request as a grocery list whose only item is
  the pantry item, so nothing is left to buy.

**12. A baseline exclusion phrasing turns a recipe into a list ("minus the olive oil").**
- *Scenario:* `test_b110`.
- *What happened:* A1 classifies the request as a grocery list and asks for an item
  quantity.

**13. A vague budget read as unsupported ("as cheap as you can"; A1).**
- *Scenario:* `test_b176`.
- *What happened:* the baseline classifies the request as `unsupported`, where the gold
  answer is a missing-budget question.
- *Related:* "I'm short on money" (`test_b197`) gets a basket without a budget question,
  from the baseline and from DistilBERT (seed 42).

**14. An unknown dish is rejected instead of asked about ("I'd like to prepare sushi").**
- *Scenarios:* `test_b161`, `test_b190`.
- *What happened:* the baseline finds no catalog dish and turns the request into an empty
  list (`invalid_request`). The gold answer is a "which dish?" question. A1 fails both.

**15. Transliterated retrieval queries fail (component, retrieval test).**
- *What happened:* MiniLM ranks paprika, potato, peanut butter and a lamb chop first for
  "kheera" (cucumber), "kali mirch" (black pepper), "makhan" (butter) and "gobhi"
  (cauliflower).
- *Scale:* transliteration Recall@10 is 0.111 for MiniLM and 0.056 for TF-IDF; the
  English model does not know the words. In the basket pipeline the parser maps aliases
  to ingredient IDs first, so this costs nothing there (case 8 maps "kali mirch"
  correctly).

**16. Associations hurt new-item recall (component, Track B test).**
- *What happened:* on each user's final order (7,413 users), the association term lowers
  NDCG@10 by 0.0105 [−0.0122, −0.0089] against personal frequency. New-item Recall@10
  falls from 0.104 to 0.073. The validation result of Phase 8 holds on test.

## What the failures say

- **With the gold request, constrained selection is reliable:** 200/200 successes, 0
  violations, all 40 infeasible cases proven, 0 timeouts. **Every end-to-end failure
  starts in the parser.**
- **DistilBERT's NLU-test lead does not carry over to baskets.**
  - On the NLU test it leads clearly: intent macro-F1 0.947 vs 0.842, exact match 0.862 vs
    0.773.
  - That lead comes from `revise_basket`, `unsupported` and list requests. On
    `plan_meal`, which is 180 of the 200 basket scenarios, the baseline is level with or
    ahead of DistilBERT on the NLU test (exact match 50/60 vs 45–50/60 across seeds).
  - In the basket test, DistilBERT is hit by held-out templates ("We're having", "I'm
    avoiding", "for a family of N, <budget>") that the baseline's dictionaries and rules
    handle.
  - Result: A1 − E4 = +0.133 [+0.062, +0.218] end to end.
  - Caveat: the baseline's cue words were written alongside the benchmark generator,
    which contains the test templates (`docs/progress.md`, Phase 5).
    No test example was parsed before the test run, but this may favour the baseline.
- **Parser errors can produce baskets labelled valid that are wrong for the user**
  (cases 9–10). The validator can only check the request it is given. A deployed system
  would need to confirm the extracted constraints with the user, which the interface
  already does under "What I understood".
- These are template-generated texts (see `docs/benchmark_policy.md`). The ranking of the
  parsers on real user text is unknown.
