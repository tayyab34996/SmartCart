# SmartCart — Build phases (full scope, single developer)

Written 2026-11-25. One person (the owner of this checkout) completes every deliverable
in the project plan, with the help of a coding agent. The deadline has been extended, so
**nothing is descoped**: every size, metric and experiment in
`SmartCart_Project_Deliverables_and_Build_Plan.docx` (repo root, git-ignored) is in scope.

**Agent instructions:** read sections 1–4 once, then work phase by phase in section 5.
Do not start a phase until the previous phase's completion check passes, unless the phase
says it can run in parallel. After each phase, update `docs/progress.md` with what changed,
the verification evidence, any open limitations and the next phase.

Deliverable IDs D1–D10 refer to the project plan.

---

## 1. Full scope (from the project plan)

| Item | Required |
|---|---|
| Recipes | ~40 curated recipes from Food.com (irkaal), spanning ≥20 meal families, manually normalized |
| Catalog | 300–500 product options with stable IDs, ingredient mapping, pack size/unit, `price_minor`, currency, availability, dietary attributes, source/`synthetic` flag per attribute, Instacart product ID where verified |
| Ingredients | Canonical ingredient IDs plus a reviewed synonym file |
| Transactions | Deterministic sample of ~10,000 Instacart users with full order history; saved sampled IDs |
| NLU annotations | 900 requests: 600 train / 150 validation / 150 test, grouped by seed, second check of ≥20% |
| Basket benchmark | 200 test scenarios (120 feasible / 40 infeasible / 40 clarification) plus 50 development scenarios |
| Retrieval queries | 150: 50 development / 100 test, with synonyms, brands, misspellings and misleading near-matches |
| Parser | Fine-tuned DistilBERT for intent and slots, 3 seeds, compared with TF-IDF + LinearSVC and regex slots |
| Retrieval | MiniLM + exact FAISS index vs TF-IDF; Recall@5, Recall@10, MRR |
| Associations | Training-only FP-Growth rules; optional history score; Track B next-basket evaluation |
| Solver | OR-Tools CP-SAT with pack-aware options, budget, pair bonuses, independent validator, accurate statuses |
| Experiments | E0–E4 and A1–A4, component-isolated and end-to-end, paired bootstrap, Track B, 5 figures, ≥10 failure analyses |
| Interface | Streamlit app with clarification, explanations, revisions and export |
| Report | 7 sections, 15-paper literature review, reproducible package, demo, viva preparation |

---

## 2. What has already been done (verified 2026-11-25)

The test suite passes: **55 passed, 95 subtests** (`.venv\Scripts\python -m pytest`).
Passing tests do **not** cover the known problems listed below.

| ID | Status | What exists | Known problems |
|---|---|---|---|
| D1 Scope | Partial | `docs/dataset_selection.md`, `docs/progress.md`; research questions are in the plan | No scope document or 15-paper comparison in the repo; `docs/literature/` is empty |
| D2 Data | Partial | Source audit (`src/smartcart/data/audit.py`, `docs/data_audit.md`), data dictionary, validated pilot catalog `data/processed/pilot/catalog.json` (20 products, 11 ingredients, 3 recipes, PKR, simulated prices), validator `validate_pilot()` and `requirements_for()` in `src/smartcart/data/contracts.py`, cleaned Instacart sample `data/processed/cleaned_instacart_data.csv` (100k rows, 9,477 orders, one order per user) | All dietary labels `unknown`; no annotations, benchmarks or splits; **raw archives are not on this machine** (`configs/data_audit.json` expects `data/raw/archive_3.zip` for Instacart and `data/raw/archive_4.zip` for Food.com); the cleaned sample has no order history, so it can't support Track B |
| D3 Baseline | Mostly done | Pack, cost and option helpers (`optimization/packs.py`, `costs.py`, `options.py`), cheapest-option selection, independent basket, 5 reference scenarios, `results/predictions/baseline_outputs.json` | **Pantry bug:** `d3_ref_02` uses pantry key `'flour'`, catalog uses `white_flour`, so pantry is ignored. Evaluator checks only status and max cost. Baseline uses keyword intent rules, not TF-IDF + SVC, and has no retrieval step. `select_lowest_cost_option` raises instead of recording a failure. |
| D4 NLU | Skeleton | Regex slots, keyword intent, TF-IDF + calibrated LinearSVC, BIO decoder, normalizer, clarification gate, metric functions | 8 training and 30 inline validation examples; Macro-F1 0.125. **DistilBERT is never trained**: `transformer_model.py` builds a random-weight 2-layer model. No entity-level slot F1. **Figure `10_nlu_training_and_comparison_curves.png` has no code that produced it — delete it.** |
| D5 Retrieval | Code done, eval flawed | TF-IDF retriever, MiniLM + FAISS `IndexFlatIP`, eligibility filter, Recall@5/10 + MRR, 150 generated queries, figure 11 | **Answer leak:** evaluation filters by the gold `required_ingredient`, which inflates MiniLM to ≈1.0. TF-IDF drops zero-score items. Dev and test share the same 11 ingredients. |
| D6 Associations | Not started | — | — |
| D7 Constrained solver | Not started | Helpers only (see D3) | — |
| D8 Interface | Not started | — | — |
| D9 Experiments | Not started | — | — |
| D10 Report and package | Not started | `README.md` covers only the early EDA notebooks | — |
| Environment | **Done** | `.venv` (Python 3.11.9), `requirements.txt`, `requirements-lock.txt` (fresh install verified), MiniLM cached | — |

Notebooks `01`–`03` (Instacart cleaning, EDA, scaling, logistic-regression ROC-AUC) are not
plan deliverables. Keep them, but do not cite their ROC-AUC as a project result.

---

## 3. Environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python -m pytest
```

- Keep the repo at a short path (the Windows 260-character limit breaks the torch install).
- MiniLM is cached and loaded with `local_files_only=True`.
- `distilbert-base-uncased` downloads once in Phase 6.
- CPU is enough for everything. A GPU notebook (Colab) is optional for 3-seed DistilBERT training.

---

## 4. Rules

### 4.1 Honesty rules (from the plan; non-negotiable)

- Never write a target or expected value as a result. Every reported number must come from a saved file produced by committed code.
- Report baseline wins, null results (for example RQ3) and missed targets as they are.
- Simulated prices stay labelled `SIMULATED`, in PKR. No real-savings claims.
- `unknown` dietary evidence never satisfies a hard dietary request.
- Tune only on development/validation data. Freeze configurations before touching any test set.
- Keep failed outputs in every denominator. A solver timeout is never reported as infeasible.
- Never claim a recipe or product source that was not actually checked.

### 4.2 Git and code

- Small commits, one function or feature each, matching the existing history style. Keep `main` passing `pytest`.
- Write new code in PEP 8 style. Do not reformat existing files wholesale.
- Never commit `models/`, `data/raw/` or files over ~20 MB.
- `data/processed/pilot/catalog.json` is **frozen** (existing tests assert 20 products and 3 recipes). The full catalog is a new file, `data/processed/catalog.json`, with the same schema.

### 4.3 Module interfaces (build modules against these)

- **Catalog** — `data/processed/catalog.json`.
  - Same schema as the pilot; must pass `validate_pilot()`.
  - Keep all pilot product and recipe IDs.
  - Units are `g`, `ml` or `piece`. Money is integer `price_minor` (paisa; 100 per PKR).
  - Dietary values are `"allowed"`, `"disallowed"` or `"unknown"` (the existing `validate_pilot()` contract), for `vegetarian`, `vegan`, `gluten_free`, `dairy_free` and `nut_free`.
  - Recipes also carry a `meal_family`; validated by `validate_catalog()`.
- **StructuredRequest** — parser output and solver input:
  ```json
  {"request_id": "s012", "intent": "plan_meal", "recipe_id": "foodcom_3474", "servings": 4,
   "items": [{"ingredient_id": "egg", "amount": "6", "unit": "piece"}],
   "pantry": {"white_flour": "250"}, "budget_minor": 150000, "currency": "PKR",
   "diet": ["vegetarian"], "exclusions": ["cheddar"], "user_id": null,
   "needs_clarification": false, "clarification_type": null, "clarification_prompt": null}
  ```
  - `intent` is one of `plan_meal`, `build_grocery_list`, `revise_basket`, `unsupported`.
  - `pantry` amounts are in the ingredient's recipe unit; `null` means unknown and triggers clarification.
  - `clarification_type` is one of `missing_recipe`, `missing_budget`, `missing_pantry_quantity`, `low_confidence_intent`, `ambiguous_diet`, or `null`.
- **Parser** — `smartcart.nlu.api.parse_request(text, catalog, parser="transformer"|"baseline", session=None) -> StructuredRequest`. `session` carries the previous request so revisions work.
- **Retrieval** — `smartcart.retrieval.api.retrieve_candidates(ingredient_id, catalog, method="minilm"|"tfidf", top_k=10) -> [{"product_id", "retrieval_score" (0–1), "rank"}]`. Rankings are over the whole catalog; retrieval never enforces hard rules.
- **Associations** — `smartcart.associations.api.pair_score(a, b) -> float in [0, 1]` (symmetric; 0.0 if unknown) and `history_score(user_id, product_or_ingredient_id) -> float in [0, 1]`.
- **Basket benchmark scenario** — `data/benchmarks/basket_{dev,test}.json`:
  ```json
  {"scenario_id": "t031", "family_id": "f11", "label": "feasible|infeasible|clarification",
   "text": "pasta for 4 under 1500 rupees, I already have 250 g flour",
   "gold_request": {"...": "StructuredRequest"}, "clarification_answer": null, "has_history": false}
  ```

---

## 5. Phases

| Phase | Deliverables | Depends on |
|---|---|---|
| 0 | Repo prep, raw data, D1 scope | — |
| 1 | Fix inherited defects (D3, D4, D5) | 0 |
| 2 | D2 full catalog and recipes | 0 |
| 3 | D2 transaction sample and Track B splits | 0 (can run alongside 2) |
| 4 | D2 benchmarks (NLU, basket, retrieval) and gold feasibility checker | 2 |
| 5 | D3 complete baseline (E0) | 1, 4 |
| 6 | D4 transformer parser | 4 |
| 7 | D5 semantic retrieval | 2, 4 |
| 8 | D6 associations and Track B | 3, 7 |
| 9 | D7 constrained solver and validator | 4, 7 |
| 10 | D8 Streamlit interface | 6, 9 |
| 11 | D9 experiments | 5–10 |
| 12 | D10 report, package, demo | 11 |

---

### Phase 0 — Repo prep, raw data, D1 scope

**Tasks**
1. Add `.gitignore` exceptions so benchmarks and results can be tracked:
   ```gitignore
   !/data/annotations/*.jsonl
   !/data/benchmarks/*.json
   !/data/splits/*.json
   !/data/processed/catalog.json
   !/data/processed/synonyms.csv
   !/data/processed/*.csv
   !/results/metrics/*
   !/results/figures/*
   ```
2. Re-acquire the raw data. This is a manual step for the user, and needs a Kaggle account.
   - Instacart Market Basket Analysis → `data/raw/archive_3.zip`
   - Food.com Recipes and Reviews (irkaal) → `data/raw/archive_4.zip`
   - Re-run `scripts/audit_data.py` and check the SHA-256 hashes against `docs/data_audit.md`.
3. Write `docs/scope.md` (D1): user scenario, core scope and future work, the contribution statement, RQ1–RQ3, the definition of success, and the PKR simulation note.
4. Ask the user to add the team's literature-matrix spreadsheet to `docs/literature/`. Start the 15-paper comparison table in `docs/literature/review.md`, to be finished in Phase 12.

**Completion check:** the audit re-runs with matching hashes; `docs/scope.md` exists; `pytest` passes.

---

### Phase 1 — Fix inherited defects

**Tasks**
1. **D3:**
   - Fix the pantry key in `src/smartcart/benchmarks/reference.py` (`'flour'` → `'white_flour'`).
   - Add hand-calculated expected lines (product, packs, cost) to each reference scenario, and make `pipeline/evaluator.py` compare them exactly.
   - Make the independent basket return status `incomplete` (with the failing ingredient) instead of raising.
   - Re-export `baseline_outputs.json`.
2. **D4:** delete `results/figures/10_nlu_training_and_comparison_curves.png` and its notebook cell; it is regenerated from real logs in Phase 6.
3. **D5:**
   - Change `retrieval/evaluation.py` so rankings are scored over the whole catalog, with no filtering by the gold ingredient.
   - Make TF-IDF keep zero-score items in a deterministic order.
   - Mark the existing `retrieval_benchmark_results.json` and figure 11 as superseded; they are regenerated in Phase 7.
4. Update the tests that encoded the old behaviour.

**Completion check:** the pantry scenario buys less flour than scenario 1; the evaluator fails a deliberately wrong expected line; a test proves the retrieval evaluator no longer receives the gold ingredient; `pytest` passes.

---

### Phase 2 — D2 full catalog and recipes

**Tasks**
1. **Recipes.**
   - Select ~40 Food.com recipes spanning ≥20 meal families from `archive_4.zip`, using the audit's structural checks.
   - For each recipe, record servings and every amount and unit explicitly.
   - Reject or manually resolve vague quantities; never invent amounts.
   - Record source and review status for each recipe.
2. **Ingredients and synonyms.**
   - Canonical ingredient IDs.
   - `data/processed/synonyms.csv` (alias, ingredient ID, reviewer, status).
   - Ingredient-specific conversions only where documented.
3. **Catalog.** 300–500 product options covering every recipe ingredient with 2–5 pack sizes or brands each, plus distractor products for misleading near-match queries.
   - Each option has a stable ID, pack amount and unit, `price_minor`, `available`, and dietary values with evidence.
   - Every simulated attribute is flagged in `simulated_fields`.
   - Match an Instacart `product_id` into `external_ids` only where the match is verified.
4. **Validation.** Extend or reuse `validate_pilot()` for the full catalog. `scripts/prepare_data.py` writes coverage statistics, duplicate checks and missing-field checks to `results/metrics/catalog_checks.json`.
5. **Data card.** `docs/data_card.md` covers sources, terms, sizes, simulation policy, the dietary policy and known gaps.

**Completion check:** `catalog.json` validates; every recipe ingredient has at least one compatible product; the counts are within the scope table; `tests/unit/test_catalog.py` passes.

---

### Phase 3 — D2 transaction sample and Track B splits (can run alongside Phase 2)

**Tasks**
1. From `archive_3.zip`, draw a deterministic (seeded) sample of ~10,000 users who have **at least five usable orders** after filtering. Save the user IDs to `data/splits/instacart_users.json`.
2. Profile memory and process in chunks.
3. **Track B split per user:** the final order is test, the preceding order is validation, and earlier orders are training. Save the manifest to `data/splits/instacart_trackb.json` and report exclusions.
4. Treat baskets as item sets; order position and the reorder flag are not quantities.
5. Map Instacart products to catalog ingredients (and to catalog products where verified). Report the mapping coverage.

**Completion check:** the sample is reproducible from its seed; the manifest exists; the counts and exclusions are recorded in `docs/data_card.md`.

---

### Phase 4 — D2 benchmarks and gold feasibility checker

**Tasks**
1. **NLU annotations.** Write `data/annotations/nlu.jsonl` with 900 examples. Each has `id`, `seed_id`, `text`, `intent`, `tokens`, `bio_tags` and the gold StructuredRequest fields.
   - Slots: meal, product, budget, currency, servings, quantity, unit, diet, exclusion, pantry item. Each quantity is attached to its item.
   - Cover negation ("no peanuts" vs "peanut butter"), word numbers, units, pantry, budget edits, exclusions and unsupported requests.
   - Split by `seed_id` into 600/150/150 in `data/splits/nlu_split.json`.
2. **Annotation check.** The plan requires a second person to check ≥20% (180 examples). Ask a teammate to review `data/annotations/review_sample.jsonl`. If nobody is available, do a delayed self-review and **disclose it** in the report. Record agreement and resolutions in `docs/annotation_review.md`.
3. **Gold feasibility checker** (`src/smartcart/validation/feasibility.py`): exhaustive enumeration over the full catalog under the supported model.
   - One product type per remaining ingredient, the minimum whole packs, diet and exclusion as eligibility, `unknown` failing hard diet rules, and the budget.
   - Returns the label and the minimum feasible cost.
   - Tests: exact budget, insufficient budget, excluded product, unknown label, pantry covers everything, multi-pack, and the worked example (600 g needed, 200 g in pantry, 250 g packs → 2 packs, 100 g surplus).
4. **Basket benchmark.**
   - `data/benchmarks/basket_test.json`: 200 scenarios (120 feasible, 40 infeasible, 40 clarification), grouped in families. Include a `has_history` subset that has Instacart-sampled users.
   - `basket_dev.json`: 50 scenarios.
   - Every label comes from the checker. Test families never appear in dev or in NLU training.
5. **Retrieval queries.** `data/benchmarks/retrieval_{dev,test}.json`: 50/100 queries with synonyms, brands, misspellings and misleading near-matches. Relevant sets come from the reviewed mappings plus a manual check. Group by ingredient so test ingredients aren't tuned on.
6. **Lock** all test files. Record their SHA-256 hashes in `docs/benchmark_lock.md`.

**Completion check:** the counts match the scope table; there is no seed or family overlap across splits (tested); every feasibility label is reproducible by the checker; the hashes are recorded.

---

### Phase 5 — D3 complete baseline (E0)

**Tasks**
1. Train the TF-IDF + LinearSVC intent classifier inside a scikit-learn `Pipeline` on the 600 training examples only.
2. Extend the regex/dictionary slot extraction to all slot types, with negation and unit rules.
3. Implement `parse_request(..., parser="baseline")`.
4. Use TF-IDF retrieval for each ingredient, independent cheapest-option selection, then post-hoc filtering. Keep incomplete outcomes as failures.
5. Run the baseline on the validation data and save its predictions.

**Completion check:** five structured requests produce itemized baskets; baseline predictions on validation are saved; the E0 configuration is in `configs/experiments/E0.json`.

---

### Phase 6 — D4 transformer parser

**Tasks**
1. `scripts/train_nlu.py`: fine-tune `distilbert-base-uncased` as two models, sequence classification for intent and token classification for BIO slots (first sub-token labelled).
   - Seeds 13, 42 and 7. Save checkpoints to `models/nlu/` (not committed).
   - Log training curves.
2. Normalization: typed budget in minor units, canonical ingredient IDs, normalized amounts, exclusions, and quantity-to-item attachment.
3. **Uncertainty:**
   - Calibrate confidence on validation data (temperature scaling or isotonic) and choose gating thresholds there.
   - Generate clarification prompts for an ambiguous budget, amount, diet or meal. For broad meal goals ("vegetarian dinner for four"), offer up to 3 supported recipes.
   - Detect unsupported requests.
4. Implement `parse_request(..., parser="transformer")` with `session` support for revisions.
5. **Metrics** (validation during development, test once frozen):
   - intent Macro-F1 and per-class scores, confusion matrix;
   - entity-level slot F1;
   - exact budget and servings accuracy;
   - quantity attachment accuracy;
   - for the transformer, mean ± spread over the 3 seeds.

   Save to `results/metrics/nlu_*.json`. Generate figure `09_` (confusion matrix) and a new figure `10_` from the real training logs.
6. Review ≥20 validation failures in `docs/nlu_failures.md` before freezing.

**Completion check:** checkpoints load locally; metrics exist for both parsers; the figures are regenerated from logs; the thresholds are frozen in a config file.

---

### Phase 7 — D5 semantic retrieval

**Tasks**
1. Encode normalized product names and short descriptions once with frozen `all-MiniLM-L6-v2`, normalize the embeddings, and build a FAISS `IndexFlatIP`. `scripts/build_index.py` caches the index along with the input hash.
2. Search per required ingredient, not per whole request.
3. Retrieve the initial top 10, then apply eligibility checks for ingredient identity, unit and diet in the solver. Similarity never proves a dietary rule.
4. Tune the candidate count on development queries only.
5. Implement `retrieve_candidates`. Fix `filter_eligible_candidates()`: it checks dietary values with `is True`, but the catalog uses `"allowed"`, so no product can currently pass a dietary filter (found in Phase 2).
6. Evaluate Recall@5, Recall@10 and MRR for TF-IDF and MiniLM under the same catalog and eligibility rules. Regenerate figure `11_` and `results/predictions/retrieval_benchmark_results.json`.

**Completion check:** dev and test results exist for both methods; test queries are evaluated once, with frozen settings; the leak-regression test passes.

---

### Phase 8 — D6 associations and Track B

**Tasks**
1. `scripts/mine_rules.py`: mine FP-Growth (mlxtend) itemsets on **training** transactions only.
   - Start with pairs and `max_len=3`, and profile memory before increasing.
   - Set a minimum count plus support and confidence thresholds on development data.
2. Use product-level rules where catalog products have verified Instacart IDs. Otherwise aggregate baskets to ingredients and say so.
3. Export `data/processed/rules.csv` with antecedent, consequent, count, support, confidence and lift. Examine the strongest rules manually.
4. Make `pair_score` a bounded transform. Never sum an unbounded number of pair scores.
5. Make `history_score` a personalized item frequency from the user's training orders.
6. **Measure whether the association term changes product selection.** If rules are ingredient-level, every brand of an ingredient gets the same score. Record this as an analysis result.
7. **Track B:** compare popularity, personalized frequency [S9] and association-enhanced ranking on the same item universe and list length. Report Recall@10 and NDCG@10 on the held-out final orders, with repeat and new items separately.
8. Write `docs/association_analysis.md` with descriptive plots, examples of helpful and misleading associations, and the Track B results.

**Completion check:** rules come from training data only (tested); the Track B metrics file exists; the analysis document says whether the score is active.

---

### Phase 9 — D7 constrained solver and validator

**Tasks**
1. Implement selection in the plan's six steps:
   1. Resolve the recipe or list, scale to servings, aggregate repeated ingredients and subtract pantry amounts.
   2. Build eligible options per ingredient: one product maps to one ingredient, and mixed bundles are excluded.
   3. For each option, compute the minimum whole packs and the option cost including all packs.
   4. CP-SAT (`src/smartcart/optimization/cpsat.py`):
      - one Boolean per option;
      - exactly one option per ingredient;
      - sum of option costs ≤ `budget_minor` (integers in minor units).
   5. Objective with explicit integer scaling: maximise normalized relevance + history + pair bonuses (AND-linked Booleans), with modest cost and surplus penalties. Hard rules stay outside the objective, and the weights are tuned on dev.
   6. An independent validator (`src/smartcart/validation/validator.py`) recomputes quantities, exclusions, diet and cost from the selected catalog IDs. A basket is shown as valid only if this passes.
2. **Statuses:**
   - `valid`
   - `needs_clarification`
   - `no_basket_in_candidate_pool`: expand retrieval within the catalog and retry
   - `infeasible_in_scope`
   - `solver_timeout`: not infeasibility
   - `unsupported`
   Log the solver status, time limit and whether optimality was proven.
3. For a budget conflict, solve a minimum-cost complete basket under the same diet rules and present the required budget as a suggestion. Never relax rules silently.
4. Clarification policy: at most three turns.
5. Generate explanations from verified records and scores (`src/smartcart/explanations/`).
6. Tests: CP-SAT vs the Phase 4 enumeration on small cases, covering exact budget, insufficient budget, excluded product, unknown label, pantry, multi-pack and timeout handling.

**Completion check:** CP-SAT agrees with enumeration on every small case; the validator rejects deliberately corrupted baskets; the objective weights and constraints are recorded in `configs/`.

---

### Phase 10 — D8 Streamlit interface

**Tasks** (`app.py`, run with `streamlit run app.py`):
- Show the request, extracted fields and any clarification question. Let the user confirm a recipe for broad meal goals.
- Show products, pack quantities, line costs, total, budget remaining and ingredient coverage, with explanations from recipe requirements and observed data.
- Support budget and exclusion edits, re-run selection, and explain what changed.
- Export the validated basket and its trace as CSV and JSON.
- Show a prominent simulated-price banner, and clear statuses: valid, clarification needed, no solution found, proven infeasible within scope.
- Optionally select a user with history.

**Completion check:** all six demo cases work: normal feasible request, budget revision, dietary exclusion, pantry quantity, unfamiliar wording, infeasible request. Cold-load and warm latency are measured.

---

### Phase 11 — D9 experiments

**Tasks**
1. `scripts/evaluate.py --config configs/experiments/<RUN>.json`:

| Run | Configuration |
|---|---|
| E0 | TF-IDF intent and retrieval, rule slots, independent selection, post-hoc filtering |
| E1 | E0 with the transformer parser |
| E2 | E1 with MiniLM retrieval |
| E3 | E2 with constrained selection |
| E4 | E3 with association-aware scoring |
| A1 | E4 with the baseline parser |
| A2 | E4 with TF-IDF retrieval |
| A3 | E4 with association weight 0 |
| A4 | E4 with independent selection and post-hoc filtering |

2. Run every configuration in two modes: **component-isolated** (gold StructuredRequest, frozen candidate pool for the selector comparison) and **end-to-end** (predicted input). Use identical scenario IDs, prices, recipes, compute limits and validation rules.
3. Write one row per scenario × run to `results/predictions/runs/<RUN>_<mode>.jsonl`. Each row holds the IDs, extracted constraints, recipe, candidates, selected products, pack counts, total, validator outcome, coverage, solver status and latency.
4. Metrics in `results/metrics/` (section 8 of the plan): score feasible, infeasible and clarification scenarios separately, and check validity against the **gold** request.
   - intent Macro-F1 and slot F1;
   - retrieval Recall@10 and MRR;
   - mean coverage;
   - valid complete success on the 120 feasible scenarios;
   - zero violations among outputs labelled valid;
   - infeasible detection on the 40, plus false rejection;
   - clarification success within 3 turns, plus unnecessary clarifications;
   - warm p50/p95 latency and cold load time;
   - Track B Recall@10 and NDCG@10.
5. Transformer runs use 3 seeds (mean and spread). Compute paired bootstrap intervals over families for the main success-rate differences.
6. Five figures: parser errors, retrieval comparison, basket success and validity, ablations, latency.
7. Write ≥10 representative failure analyses in `docs/failure_analysis.md`.

**Completion check:** every run and mode has JSONL and metrics files; one command reproduces each report table from a named configuration; the test sets were evaluated with frozen configs only.

---

### Phase 12 — D10 report, package and demo

**Tasks**
1. Finish the **literature review**:
   - a synthesis of 15 papers; read the methods and results of the closest work: constrained food QA [S7], ReCANet [S12], the next-basket reality check [S8], Sentence-BERT [S10] and ChatCRS [S11];
   - check the lecture's allowed venues and the meaning of "recent";
   - do not describe the approach as globally unique.
2. **Report** (`docs/report/`), with the abstract written last:

| Section | Contents |
|---|---|
| Abstract | Problem, actual approach, datasets, main measured result, scope limitation |
| Introduction | Scenario, RQs, scope, contribution, success definition |
| Literature review | The 15-paper synthesis |
| Methodology | Data flow, mappings, models, constraints, splits, baselines, metric definitions |
| Implementation | Modules, environment, training setup, catalog assumptions, solver handling |
| Results and discussion | Comparisons, uncertainty, ablations, failures, runtime, limitations |
| Conclusion | An answer to each RQ, measured contributions, open issues |

3. **README:** setup, the reproducible commands (`prepare_data`, `train_nlu`, `build_index`, `mine_rules`, `evaluate`, `streamlit run app.py`), data acquisition instructions and terms, model download and checkpoint instructions, and sample inputs.
4. **Clean-environment run:** a fresh `.venv` from the lock file, then `pytest`, then the full evaluation reproduces the report tables.
5. Record seeds, package versions, model revisions, source versions and input hashes in `results/run_manifest.json`.
6. Rehearse the demo (the six cases from Phase 10).
7. **Viva preparation:** be able to explain one request end to end, justify the baseline, describe one failure and interpret one ablation.

**Completion check:** the plan's final submission checklist is satisfied:
- the report has all sections, consistent references, and clear labels for simulated data and assumptions;
- every table traces to a config, a prediction file and a metric calculation;
- the code package includes the README, pinned environment, data instructions, sample inputs, tests and model instructions;
- the demo covers the six cases;
- the contribution summary, limitations, dataset terms and any required declaration of AI or tool assistance are included.

---

## 6. Proposed engineering targets (report actual values, explain misses)

| Area | Target |
|---|---|
| Intent Macro-F1 (locked test) | ≥ 0.85 |
| Slot entity F1 / exact numeric fields | ≥ 0.85 / ≥ 95% |
| Retrieval Recall@10 | ≥ 0.90 (report the lexical comparison) |
| Mean coverage on feasible scenarios | ≥ 95% |
| Valid complete success (120 feasible) | ≥ 90%, compared with E0 |
| Violations among outputs labelled valid | 0 |
| Infeasible detection (40) | ≥ 90%, with false rejections reported |
| Clarification completion within 3 turns (40) | ≥ 85% |
| Warm p95 latency | < 5 s on the stated laptop |
| Track B | Compare with popularity and frequency; no guaranteed improvement |

These are targets, not results.
