# NLU validation failure review (Phase 6)

The plan requires a review of at least 20 validation failures before the parser is frozen.
This file reviews **all 45** request-level failures of the DistilBERT parser on the 150
validation examples (3 seeds × 150 = 450 parses; whole-request exact match 405/450).
It also covers E0's 4 failures, for comparison. Test data was not used.

Sources: `results/predictions/nlu_dev_transformer_seed{13,42,7}.jsonl`,
`results/predictions/E0_nlu_dev.jsonl`, `results/metrics/nlu_dev.json`.

## Summary by cause

| # | Cause | Seed 13 | Seed 42 | Seed 7 | Total |
| --- | --- | --- | --- | --- | --- |
| 1 | "N portions": number tagged QUANTITY or BUDGET, "portions" tagged UNIT | 0 | 6 | 1 | 7 |
| 2 | Pantry vs product role swapped | 4 | 3 | 2 | 9 |
| 3 | Intent: "Can we do it for X instead" read as `unsupported` | 3 | 0 | 3 | 6 |
| 4 | Diet wording split: "without gluten", "nut free" | 2 | 2 | 2 | 6 |
| 5 | Intent: grocery list read as `plan_meal` | 2 | 1 | 2 | 5 |
| 6 | Multi-word ingredient broken into pieces | 1 | 1 | 3 | 5 |
| 7 | Span runs past the item: "chicken cutlet left" | 3 | 0 | 0 | 3 |
| 8 | Slot missed entirely ("keto", "hold the water") | 0 | 2 | 0 | 2 |
| 9 | Number words cut short: "one thousand" → "one" | 0 | 1 | 0 | 1 |
| 10 | Meal boundary: "baked" split from "sweet potato fries" | 0 | 1 | 0 | 1 |
| | **Total** | **15** | **17** | **13** | **45** |

**Main finding.** 31 of the 45 failures (causes 1, 2, 3, 7, 8) involve validation-only
phrasing that no training example contains: "N portions", "I have X left", "found X in
the fridge", "throw in X", "hold the X", "can we do it for X instead". Validation
templates are held out from training on purpose (`docs/benchmark_policy.md`), and the
fine-tuned tagger leans on template context more than on the item words. The E0 rules
key on the catalog vocabulary, which every split shares, so they barely notice the new
templates. E0 fails only 4 validation requests, all of them intent errors.

## Reviewed failures

Each row: example, seed, text, what went wrong, and the effect on the request.

| # | Example (seed) | Text | Error | Effect |
| --- | --- | --- | --- | --- |
| 1 | dev-plan-006-p0 (42, 7) | "…no more than PKR 5200 and 6 portions, I have 100 millilitres ricotta left" | "6" tagged QUANTITY (no item follows, so nothing attaches) | servings lost (null instead of 6) |
| 2 | dev-plan-006-p2 (42) | "…no more than Rs. 5,200. 6 portions. …" | "." tagged CURRENCY, "6" tagged BUDGET | budget kept (first BUDGET span wins), servings lost |
| 3 | dev-plan-016-p1 (42) | "…spend up to 1250 rupees, two portions" | "two" QUANTITY, "portions" UNIT | servings lost |
| 4 | dev-plan-002-p2 (42) | "…two portions, there's a bit of namak in my pantry…" | "two" QUANTITY, attached to "namak" | pantry salt = 2 instead of unknown; the missing-quantity question is never asked |
| 5 | dev-plan-009-p2 (42) | "I have two tsp namak left, spend up to rs 3612, 4 portions" | "4" QUANTITY | servings lost |
| 6 | dev-plan-019-p1 (42) | "Thinking of making lemon chicken, six portions. …" | "six" QUANTITY | servings lost |
| 7 | dev-revise-005-p0/p1/p2 (13) | "Throw in 500 grams long grain rice" | item tagged PANTRY instead of PRODUCT | the user's added item becomes stock they already have, so the basket shrinks instead of growing |
| 8 | dev-revise-003-p1/p2 (42, 7, 13) | "Found 1 tbsp fresh lemon juice in the fridge" | PANTRY tagged PRODUCT | lemon juice is bought instead of subtracted |
| 9 | dev-plan-002-p0 (42) | "…there's a bit of salt in my pantry…" | PANTRY tagged PRODUCT; in a meal request, products are ignored | the missing-pantry-quantity question is never asked |
| 10 | dev-plan-011-p1 (7) | "…hold the groundnuts, no more than 1900 rupees" | EXCLUSION tagged PANTRY | asks "how much peanuts do you have?" (unnecessary question) and the exclusion is lost |
| 11 | dev-revise-000-p0 (13) | "Can we do it for 4,000 instead" | intent `unsupported` (confidence 0.51); budget not tagged | the revision is dropped; the user gets "unsupported" |
| 12 | dev-revise-007-p0 (13, 7) | "Can we do it for 1k instead" | intent `unsupported` | as above |
| 13 | dev-revise-007-p1 (13) | "Can we do it for one thousand instead" | intent `unsupported` (0.499) | **caught by the low-confidence gate** (threshold 0.5), so the user is asked to rephrase rather than told "unsupported" |
| 14 | dev-revise-000-p1 (7) | "Can we do it for four thousand PKR instead" | intent `unsupported` (0.55) | revision dropped; seed 7's threshold is 0, so it is not caught |
| 15 | dev-plan-012-p0 (all) | "…5 portions, without gluten" | "without" and "gluten" tagged as separate DIET (or EXCLUSION) spans | both normalise to `ambiguous`, so the parser asks which diet (unnecessary) and gluten-free is never applied |
| 16 | dev-plan-014-p1 (all) | "I feel like nut free turkey burgers…" | "nut" DIET, "free turkey burgers" MEAL | the meal does not normalise, so the parser asks for a dish (unnecessary) and nut-free is lost |
| 17 | dev-list-009-p0 (all) | "I want dijon and 250 ml worcestershire sauce, spend up to rs 2800" | intent `plan_meal` ("I want" opens many meal requests); "dijon" tagged MEAL by seed 13 | the parser asks for a dish instead of the dijon quantity. **E0 makes the same intent error.** |
| 18 | dev-list-009-p1 (13) | "Pick up dijon mustard and 250 ml worcestershire sauce…" | intent `plan_meal` (0.73) | as above |
| 19 | dev-list-007-p2 (7) | "I want 500g cheddar cheese, two l of chicken broth…" | intent `plan_meal` (0.81) | asks for a dish; the list is lost |
| 20 | dev-revise-009-p0 (13, 7) | "Drop the extra virgin olive oil" | spans "extra", "virgin olive", "oil" | no piece normalises to an ingredient; the exclusion is lost |
| 21 | dev-list-008-p1 (7) | "…500g long grain rice…" | "long" and "grain rice" split | the rice line is dropped from the list |
| 22 | dev-revise-003-p0 (42) | "Found one tablespoon fresh lemon juice in the fridge" | "fresh" / "lemon" / "juice" split across labels | the pantry update is lost |
| 23 | dev-plan-009-p1 (13) | "…I have 2 teaspoons table salt left" | PANTRY span "table salt left" | the alias lookup fails (fuzzy ratio < 0.85), so the pantry update is lost |
| 24 | dev-plan-019-p0/p1 (13) | "I have 4 chicken cutlet left" | PANTRY "chicken cutlet left" | as above |
| 25 | dev-plan-008-p1 (42) | "…feeding four, keto please" | "keto" not tagged | the ambiguous-diet question is never asked |
| 26 | dev-plan-010-p2 (42) | "…two portions, hold the water, spend up to 900 PKR" | "water" not tagged | water is bought despite the exclusion |
| 27 | dev-revise-007-p1 (42) | "Can we do it for one thousand instead" | BUDGET "one" only | budget set to 1 rupee (100 minor units) |
| 28 | dev-plan-012-p1 (42) | "Thinking of making gluten free baked sweet potato fries, spend up to rupees 900. 5 portions" | MEAL split into "baked" + "sweet potato fries"; "." CURRENCY; "5" BUDGET | recipe still found (first resolvable span); servings lost |

### Probe outside the validation set (not counted above)

During testing, the hand-written request "I want to make homemade pasta for 2 under 1500
rupees" was parsed by all three seeds. Seeds 42 and 7 tagged "2" (seed 42: "2 under") as
a BUDGET, so the first budget span gave a budget of 2 rupees. With the training-style
commas ("…, for 2 people, under 1500 rupees") all seeds parse it correctly. Training
text always separates clauses with a comma, "and" or a full stop, and the tagger relies
on that. The E0 rules parse both versions correctly.

## E0 failures (for comparison)

E0 fails 4 of 150 requests, and all 4 are intent errors:

- dev-list-009 (3 paraphrases): list → `plan_meal`. These are the same examples that
  DistilBERT gets wrong.
- dev-plan-006-p0: a meal request with a pantry clause → list.

Its slot errors (12 false negatives, all PRODUCT/QUANTITY/UNIT) come from those
mis-classified lists, because E0 only emits PRODUCT spans in lists and revisions.

## Decisions before freezing

- **No change to the trained models or the training data after this review.** Every
  cause above points at held-out phrasing. Adding those phrasings to training would make
  validation no longer held out, and inventing new templates would be guessing at the
  test set. The models are frozen as trained.
- **The calibration is frozen as fitted** (`configs/nlu_transformer.json`):

  | Seed | Temperature | ECE before → after | Threshold |
  | --- | --- | --- | --- |
  | 13 | 1.10 | 0.025 → 0.023 | 0.5 |
  | 42 | 1.25 | 0.048 → 0.022 | 0 |
  | 7 | 1.35 | 0.049 → 0.030 | 0 |

  For seeds 42 and 7, no threshold caught more wrong intents than it questioned correct
  ones, so the gate is off for them. Seed 13's threshold of 0.5 rests on a **single**
  validation example (#13 above) and should be read as weak evidence.
- **Not applied, possible future variants:**
  - lexicon-constrained decoding: snap predicted item spans to the longest catalog alias
    that overlaps them, which would fix causes 6 and 7;
  - a hybrid that takes intent from DistilBERT and slots from the E0 rules.

  Both would be new system variants. Neither is in the experiment plan (E0–E4, A1–A4),
  so adding one needs the owner's decision before Phase 11.
- **Decision (2026-11-28, before any test data was read): no variant is added.** The
  owner left the choice to the teammate building Phases 7–11, who chose to run E0–E4 and
  A1–A4 exactly as planned. The reasons:
  - **The plan already answers the question.** A1 (E4 with the baseline parser) measures
    the E0 rule slots inside the full pipeline on test.
  - **The hybrid would add little.** With the shared context rules applied, E0 is already
    level with or ahead of DistilBERT on intent on dev (0.978 vs 0.972 ± 0.016), so the
    hybrid would be close to the E0 parser.
  - **No post-hoc tuning.** Both variants were designed from these dev failures, and
    snapping would be tuned to two specific causes.

  Phase 11 reports the parsers as frozen here.
