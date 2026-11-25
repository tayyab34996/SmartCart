# Annotation review (Phase 4)

The plan requires a second person to check at least 20% of the NLU annotations (180 of
900). This file records what has been done so far and what is still pending.

## Status

| Check | Status |
| --- | --- |
| Automated integrity checks on all 900 examples | **Done, all pass** (`results/metrics/benchmark_checks.json`, `tests/unit/test_benchmarks.py`) |
| Review of the 180-example sample by the build agent | **Done, two rounds** (below) |
| Independent second-person review of the same 180 | **Pending.** Needs a teammate. If nobody is available, a delayed self-review by the project owner must be done and **disclosed in the report**. |

The build agent also wrote the generator, so its review is **not independent**. It
catches generator bugs, but it cannot stand in for the second-person check.

## Sample

`data/annotations/review_sample.jsonl` holds 180 examples, 20% of each split
(120 train, 30 dev, 30 test). They are chosen by a seeded hash of the example ID, so the
same IDs are sampled after every rebuild. Each row has the text, tokens, BIO tags, the
session (for revisions), the gold request, and blank review fields (`intent_ok`,
`slots_ok`, `gold_ok`, `notes`) for the second reviewer.

## Automated checks (all 900 examples)

- Tokens equal the tokenizer output for the text. BIO tags decode to exactly the stored
  spans, and every span's text matches its character offsets.
- Span values agree with the gold request: the meal is the gold recipe, the budget × 100
  is the gold `budget_minor`, and product, pantry and exclusion values appear in the gold
  lists.
- Every `QUANTITY` and `UNIT` span is attached to a `PRODUCT` or `PANTRY` span.
- Paraphrases of one seed share the same gold request, and no two are identical.
- No seed or family crosses splits, and no text appears in two splits.
- No `DIET` span uses "lactose" wording, and no `EXCLUSION` span includes its negation cue.

## Agent review, round 1 (first generator version)

All 180 examples were read and compared with their gold requests.

| Finding | Examples | Type | Resolution |
| --- | --- | --- | --- |
| "lactose-free" annotated as `dairy_free` (lactose-free milk is still dairy) | 3 | **Gold error** | Removed from the dairy-free forms. A test asserts that no `DIET` span uses it. |
| "keep it below X" when X equals the minimum cost (the scenario is labelled feasible under the inclusive-cap policy, but the wording reads as strict) | 2 | **Gold/text conflict** | Strict templates are never used for exact-budget designs. A check confirms zero occurrences in the NLU and basket files. |
| Ungrammatical unsupported requests ("Could you how many calories are in rice") | 3 | Text | Question-style acts rewritten as imperatives. |
| "I'm out of 500 g black beans" (odd with quantities) | 2 | Text | Template replaced ("I need to restock ..."). |
| Number agreement on ingredient nouns ("six egg", "one corn tortillas", "2 chicken thigh") | 8 | Text, cosmetic | **Not fixed.** Gold labels are unaffected. Recorded as a limitation. |

Round 1 found **5 gold-label problems in 180 (2.8%)**. All came from generator rules,
so they were fixed in the generator, and the fixes apply to the whole dataset.

## Agent review, round 2 (regenerated data)

The regenerated 180 examples were read again.

- **No gold errors found.**
- One ungrammatical text remained ("Help me tell me how much protein is in an egg") and
  was fixed by rewording the test acts.
- Counting identical paraphrases found 27 seeds whose three paraphrases were not all
  distinct. They were in dev and test unsupported requests and in vague-budget or diet
  revisions, where a split had only one template. Templates were added, and a check
  (`no_duplicate_paraphrase_within_seed`) now enforces distinct paraphrases.

## For the second reviewer

1. Open `data/annotations/review_sample.jsonl`. For each row, fill in `intent_ok`,
   `slots_ok` and `gold_ok` (true or false) and any `notes`. Judge against
   [benchmark_policy.md](benchmark_policy.md), not personal preference.
2. Report agreement as the share of rows where all three are true, plus counts per
   problem type.
3. Resolve disagreements by fixing the generator, never by hand-editing data files.
   Then rebuild, re-lock, and record the change in `docs/progress.md`.
