# SmartCart progress and direction

The build is organised in phases defined in [BUILD_PHASES.md](BUILD_PHASES.md).
Each phase starts only with the project owner's permission.

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Repo prep, raw data, D1 scope | **Complete — 2026-11-25** (one external input outstanding: the team literature matrix) |
| 1 | Fix inherited defects (D3, D4, D5) | **Complete — 2026-11-25** |
| 2 | D2 full catalog and recipes | **Complete — 2026-11-25** (independent recipe review pending) |
| 3 | D2 transaction sample and Track B splits | **Complete — 2026-11-25** (mapping review by a single reviewer) |
| 4 | D2 benchmarks and gold feasibility checker | **Complete — 2026-11-25** (second-person annotation review pending) |
| 5 | D3 complete baseline (E0) | **Complete — 2026-11-26** (validation only; test sets untouched) |
| 6 | D4 transformer parser | **Complete — 2026-11-26** (validation only; test evaluated in Phase 11) |
| 7 | D5 semantic retrieval | **Complete — 2026-11-28** (validation only; test evaluated in Phase 11) |
| 8 | D6 associations and Track B | **Complete — 2026-11-28** (validation only; Track B test evaluated in Phase 11) |
| 9 | D7 constrained solver and validator | **Complete — 2026-11-28** (dev only; test scenarios run in Phase 11) |
| 10 | D8 Streamlit interface | **Complete — 2026-11-28** |
| 11 | D9 experiments | **Complete — 2026-11-28** (test sets evaluated once, frozen configs) |
| 12 | D10 report, package and demo | In progress (clean-environment run pending) |

## Phase 11 — D9 experiments (complete, 2026-11-28)

**What changed**

- **Run configs** `configs/experiments/{E1,E2,E3,E4,A1,A2,A3,A4}.json` (E0 unchanged since
  Phase 5). Each names its parser, retrieval method, product text, candidate count,
  selector, filtering and (constrained runs) history and pair weights:

  | Run | Parser | Retrieval | Selection |
  | --- | --- | --- | --- |
  | E0 | baseline | TF-IDF, legacy text, top 10 | independent cheapest, post-hoc filter |
  | E1 | DistilBERT | as E0 | as E0 |
  | E2 | DistilBERT | MiniLM, frozen text, top 40 | as E0 |
  | E3 | DistilBERT | as E2 | CP-SAT, history 0, pair 0 |
  | E4 | DistilBERT | as E2 | CP-SAT, history 0.1, pair 0.1 |
  | A1 | baseline | as E4 | as E4 |
  | A2 | DistilBERT | TF-IDF, frozen text, top 40 | as E4 |
  | A3 | DistilBERT | as E4 | CP-SAT, history 0.1, pair 0 |
  | A4 | DistilBERT | as E4 | independent cheapest, post-hoc filter (= E2 by construction) |

- **`configs/experiments/evaluation.json`:** the run list, split, lock file, data paths,
  the two modes, seeds 13/42/7, the bootstrap settings, the nine planned comparisons and
  every output path.
- **`src/smartcart/pipeline/experiment.py`:** one scenario through a run (parse with
  up to 3 clarification turns, candidates, selection, validation), scoring against the
  **gold** request, per-run metrics, mean and spread over seeds, and the paired
  bootstrap over the 24 scenario families. Infeasibility counts as detected only through
  `over_budget`/`incomplete` (independent selector) or `infeasible_in_scope` (CP-SAT); a
  timeout never counts.
- **`scripts/evaluate.py --config configs/experiments/<RUN>.json`:** one run, both modes.
  On the test split it verifies `docs/benchmark_lock.md` first and refuses the dev-only
  options (`--seeds`, `--dev-parser`). Writes
  `results/predictions/runs/<RUN>_<mode>[_seed<N>].jsonl`,
  `results/metrics/runs/<RUN>.json` and `<RUN>_latency.json` (cold load measured from
  process start).
- **`scripts/evaluate_components.py`:** the test evaluations deferred from Phases 6–8:
  NLU (baseline and 3 DistilBERT seeds), retrieval (3 settings) and Track B (history =
  training + validation orders, rules from training orders only). Writes
  `results/metrics/test_components.json` and the per-example rows.
- **`scripts/make_report.py [--check]`:** `results/metrics/phase11_summary.json`, the
  tables `results/tables/{nlu,retrieval,baskets,comparisons,track_b}.md` (checked) and
  `latency.md` (machine-dependent, not checked), and figures 14–18.
- **`scripts/evaluate_all.py [--check]`:** lock check → components → the nine runs →
  report. This is the one command behind every report table.
- **`.gitignore`:** `results/tables/` is now tracked, so `make_report.py --check` works on
  a fresh clone.
- **`docs/failure_analysis.md`:** 16 cases from the test rows.
- **`tests/unit/test_experiments.py`** (12 tests): every planned run has a frozen config
  and the runs differ exactly as planned; the lock check; dev-only options refused on
  test; which statuses count as detected infeasibility per selector; false rejections and
  unnecessary questions; the harness reproduces the committed E0 and Phase 9 dev results; the family
  bootstrap; and, once test outputs exist, rows and metrics for every run, mode and seed,
  the 120/40/40 composition, every comparison present, and `make_report.py --check`.

**How the test run was done**

- The harness was first exercised on the **dev** split only (baseline parser,
  `--dev-parser`; outputs in `data/interim/phase11_dev`, not committed).
- The test split was then evaluated **once**, on the team's Windows laptop, with
  `scripts/evaluate_all.py` (2026-11-28, 17:01–17:33 local time, log in
  `data/interim/setup/phase11.log`). All five locked files matched
  `docs/benchmark_lock.md`. No config, code or threshold was changed after it.
- **Deviation from the plan, recorded honestly:** the Phase 11 configs and harness were
  meant to be committed before the test run; that commit was skipped, so the run used
  uncommitted files (HEAD was `e6f9ff4`). The SHA-256 checksums of all nine new config
  files were taken when they were copied to the machine and again after the run, and are
  identical; the files are committed unchanged in this phase. Everything the configs
  point to (`configs/nlu_transformer.json` and the checkpoints, `configs/retrieval.json`,
  `configs/associations.json`, `configs/solver.json`) was committed in Phases 6–9.

**Verification evidence (the team's Windows machine)**

- `scripts/evaluate_all.py --check` (2026-11-28, 18:23–18:56 local time): the lock check
  passed, then the components, all nine runs and `make_report.py` rebuilt in memory and
  matched the committed files exactly (80 `same` lines, 0 differences). The test-run
  results are deterministic on this machine; latency files are not part of the check.
- All eleven earlier `--check` scripts pass. `pytest -q`: **253 passed, 95 subtests** in
  8 min 53 s (241 before, plus 12 in `test_experiments.py`). Log:
  `data/interim/setup/phase11_check.log`.
- **Completion check:** every run and mode has rows and metrics files; `evaluate_all.py`
  reproduces every report table from the named configs; the test sets were evaluated with
  frozen configs only.

**Results (test split)**

NLU, 150 examples (`results/tables/nlu.md`):

| Parser | Intent macro-F1 (classifier only) | Intent macro-F1 | Slot micro-F1 | Request exact match |
| --- | --- | --- | --- | --- |
| E0 baseline | 0.788 | 0.842 | 0.947 | 0.773 |
| DistilBERT (mean ± std, 3 seeds) | 0.936 ± 0.034 | 0.947 ± 0.028 | 0.972 ± 0.003 | 0.862 ± 0.006 |

Budget exact: baseline 0.990, DistilBERT 0.971–0.981; servings exact: baseline 1.000,
DistilBERT 0.974–0.987. Unnecessary clarifications: 14 and 14–16.

Retrieval, 100 queries (`results/tables/retrieval.md`):

| Setting | Recall@5 | Recall@10 | MRR | R@10 transliteration |
| --- | --- | --- | --- | --- |
| TF-IDF, legacy text, top 10 (E0) | 0.552 | 0.610 | 0.562 | 0.056 |
| TF-IDF, frozen text | 0.549 | 0.610 | 0.555 | 0.056 |
| MiniLM, frozen text | 0.696 | 0.764 | 0.713 | 0.111 |

Baskets, 200 scenarios: 120 feasible, 40 infeasible, 40 clarification
(`results/tables/baskets.md`; end-to-end DistilBERT runs are the mean over 3 seeds):

| Run | Mode | Feasible success | Coverage | Violations among valid | Infeasible detected | False rejections | Clarification success | Unnecessary questions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E0 | gold input | 112/120 | 0.976 | 0 | 40/40 | 18 | 30/40 | 0 |
| E0 | end to end | 109/120 | 0.959 | 0 | 39/40 | 19 | 26/40 | 2 |
| E1 = E2 = A4 | end to end | 92.0 (91–93) | 0.851 | 3.0 (2–4) | 32.7 | 19.0 | 27.0 | 23.0 |
| E3 = E4 = A2 = A3 | gold input | 120/120 | 1.000 | 0 | 40/40 | 0 | 40/40 | 0 |
| E3 = E4 = A2 = A3 | end to end | 97.0 (96–98) | 0.822 | 3.0 (2–4) | 32.7 | 5.3 | 35.7 | 23.0 |
| A1 | end to end | 117/120 | 0.975 | 0 | 39/40 | 1 | 36/40 | 2 |

E1, E2 and A4 with gold input equal E0 (112/120, 18 false rejections); A1 with gold input
equals E4. There were **0 solver timeouts** in every run.

Paired differences in scenario success, 95% bootstrap interval over families
(`results/tables/comparisons.md`):

| Comparison | Gold input | End to end |
| --- | --- | --- |
| E1 − E0 (parser) | 0 | **−0.112** [−0.191, −0.048] |
| E2 − E1 (retrieval) | 0 | 0 |
| E3 − E2 (constrained selection) | **+0.090** [+0.064, +0.117] | **+0.068** [+0.041, +0.096] |
| E4 − E3 (association terms) | 0 | 0 |
| E4 − E0 (full system vs baseline) | **+0.090** [+0.064, +0.117] | −0.043 [−0.131, +0.032] |
| A1 − E4 (baseline parser) | 0 | **+0.133** [+0.062, +0.218] |
| A2 − E4 (TF-IDF retrieval) | 0 | 0 |
| A3 − E4 (pair weight 0) | 0 | 0 |
| A4 − E4 (independent selection) | **−0.090** [−0.117, −0.064] | **−0.068** [−0.096, −0.041] |

Track B, final order of 7,413 users (2,587 excluded: no mapped ingredient in the target
order) (`results/tables/track_b.md`):

| Ranker | Recall@10 | NDCG@10 | New-item Recall@10 |
| --- | --- | --- | --- |
| Popularity | 0.502 | 0.361 | 0.261 |
| Personal frequency | 0.703 | 0.582 | 0.104 |
| Frequency + association | 0.686 | 0.572 | 0.073 |

Association − frequency: NDCG@10 −0.0105 [−0.0122, −0.0089], Recall@10 −0.0170
[−0.0204, −0.0135]. Frequency − popularity: NDCG@10 +0.221 [+0.215, +0.229].

Latency (`results/tables/latency.md`, Windows 10 laptop, 4 CPUs): warm end-to-end p95 per
scenario ≤ 0.42 s in every run (E2 highest; A1 0.035 s). Cold load 8.0 s for E0, 19.1 s
for A1 (MiniLM), 24.5–31.9 s for DistilBERT runs.

**Targets against actual values** (BUILD_PHASES section 6)

| Target | Actual | |
| --- | --- | --- |
| Intent macro-F1 ≥ 0.85 | DistilBERT 0.947; baseline 0.842 | met (DistilBERT) / missed (baseline) |
| Slot F1 ≥ 0.85 | 0.972 / 0.947 | met |
| Exact numeric fields ≥ 95% | NLU test: budget 0.971–0.990, servings 0.974–1.000 | met |
| Retrieval Recall@10 ≥ 0.90 | MiniLM 0.764 (TF-IDF 0.610) | **missed** |
| Mean coverage ≥ 95% | gold input 1.000; E4 end to end 0.822; A1 0.975 | met with gold input and A1; **missed** by E4 end to end |
| Valid complete success ≥ 90% | E4 gold 100%; E4 end to end 80.8%; A1 97.5%; E0 end to end 90.8% | met except E4 end to end |
| 0 violations among valid | 0 with gold input and for the baseline parser; 2–4 per DistilBERT seed end to end | **missed** end to end with DistilBERT |
| Infeasible detection ≥ 90% | gold 100%; E4 end to end 81.7%; A1 97.5% | met except E4 end to end |
| Clarification within 3 turns ≥ 85% | E4 end to end 89%; A1 90%; E0 end to end 65% | met by E4 and A1 |
| Warm p95 < 5 s | ≤ 0.42 s | met |
| Track B: compare with baselines | frequency beats popularity; association lowers both metrics | reported |

**Findings to carry into the report**

- **RQ2 (constrained selection) — yes.** With the gold request, CP-SAT solves all 200
  scenarios: every feasible basket valid, all 40 infeasible cases proven with a suggested
  budget, 0 violations, 0 timeouts. E0's 18 failures are all diet scenarios where the
  post-hoc filter drops a cheapest product that is `unknown` for the diet. The gain holds
  end to end (+0.068).
- **RQ1 (semantic retrieval) — better matching, no basket effect.** MiniLM beats TF-IDF by
  0.154 Recall@10 on free-text queries, but E2 − E1 and A2 − E4 are exactly 0: the
  pipeline queries canonical ingredient names, for which both pools contain the right
  products. Transliterations stay unsolved by both (0.111 and 0.056).
- **RQ3 (associations) — null on baskets, negative on Track B.** E4 = E3 and A3 = E4 on
  every scenario (the terms cannot change selection, as Phase 8 showed). On Track B the
  association term lowers NDCG@10 and new-item recall; the validation result holds on
  test.
- **The parser decides the end-to-end result, and the baseline wins.** DistilBERT leads on
  the NLU test, but A1 (baseline parser) beats E4 by +0.133 end to end and E1 is below E0
  by −0.112. DistilBERT's NLU lead is on revision, unsupported and list requests; on
  `plan_meal`, 180 of the 200 basket scenarios, the baseline is level or ahead (exact
  match 50/60 vs 45–50/60). The basket test uses
  phrasings never seen in training ("We're having", "I'm avoiding", "for a family of N,
  <budget> is my limit"), which the baseline's rules handle and DistilBERT often does not
  (`docs/failure_analysis.md`, cases 3–8).
- **Caveat on the baseline's win:** its cue words were written by a build agent that had
  read the benchmark generator, which contains the test templates (Phase 5 limitation).
  No test example was parsed before the test run, but the report must state that A1 may
  be favoured by this.
- **Parser errors can produce baskets labelled valid that are wrong for the user** (2–4 per
  DistilBERT seed: a missed "no meat", missed servings). The validator checks the request
  it is given; the interface's "What I understood" panel is the safeguard.
- The best end-to-end system measured is **A1** (baseline parser, MiniLM, CP-SAT):
  192/200, 0 violations, 39/40 infeasible detected, 1 false rejection.

**Open limitations**

- All basket and NLU texts are template-generated (`docs/benchmark_policy.md`); the
  parsers' ranking on real user text is unknown.
- Prices are simulated PKR; no savings claim is possible.
- The pre-run commit was skipped (see above); integrity rests on the recorded checksums.
- Latency is from one laptop and is not part of `--check`.
- Outstanding from earlier phases: the second-person annotation review (Phase 4) and the
  independent recipe and Instacart-mapping reviews.

## Phase 10 — D8 Streamlit interface (complete, 2026-11-28)

**What changed**

- **`app.py`** (run with `.\.venv\Scripts\python -m streamlit run app.py`). It only draws
  widgets; every value comes from the frozen pipeline:
  - a prominent simulated-price banner;
  - "What I understood": the extracted fields, including the optional history user;
  - a clarification question with an answer box. A broad meal goal ("something
    vegetarian") lists up to 3 feasible, cheapest-first dishes to confirm, or any other
    dish;
  - the status: valid basket, clarification needed, no solution found (a timeout, or no
    basket in the pool), or proven infeasible within scope. An infeasible budget gets a
    "use the suggested budget" button;
  - the basket table (packs, pack size, need, bought, left over, line cost, cheapest
    eligible), the total, budget remaining, ingredient coverage and number of products;
  - "Why these products" (explanations from verified records) and the notes on pantry,
    exclusions and the validator;
  - budget, exclusion and diet edits, or a revision in words through the parser's
    revision rules, each followed by **"What changed"**;
  - CSV export of the basket and JSON export of the basket, trace and conversation;
  - a sidebar: the parser (DistilBERT by default; the E0 baseline, with a note, when the
    checkpoints are missing) and an optional shopper with purchase history.
- **`src/smartcart/app/session.py`:** the interface logic, testable without Streamlit:
  parse, answer, revise, recipe suggestions and confirmation, edit, run, status view,
  basket rows, coverage, request fields, changes and exports.
  - "What changed" compares lines only when both runs have a basket. When a change makes
    the request infeasible, it says the previous basket no longer applies, rather than
    listing every line as removed.
- **`smartcart.nlu.api.get_parser`:** returns the cached parser object, used by
  `parse_request` and the app. `evaluate_nlu.py --check` and `run_baseline.py --check`
  confirm that nothing changed.
- **`configs/app.json`:** the parser and fallback, the solver config, the history-user
  list and the **six hand-written demo cases**. None of the demo texts appears in the
  annotations or the basket benchmarks (tested).
- **`scripts/run_demo_cases.py [--check]`:** runs each demo conversation through
  `session` with the app's parser and writes `results/metrics/demo_cases.json`.
- **`scripts/measure_app_latency.py`:** runs `app.py` headless (Streamlit `AppTest`) in a
  fresh process and writes `results/metrics/app_latency.json` (machine-dependent, not
  part of `--check`).

**Verification evidence (the team's Windows machine, DistilBERT parser)**

| Demo case | Steps | Final status |
| --- | --- | --- |
| D1 normal feasible request | parse (history user selected) | valid, PKR 2,407 of 2,500 |
| D2 budget revision | parse → "Actually, can we do it for 1,200 rupees instead" | proven infeasible, suggested budget PKR 2,192; "what changed" names the budget |
| D3 dietary exclusion | "Something vegetarian for dinner for 3…" → dish suggestions → confirm → exclude the dearest line | valid; butter removed, total PKR 727 → 487 |
| D4 pantry quantity | parse → "How much onion do you already have (in piece)?" → "I have 2 onions" | valid, PKR 1,847 of 2,000 |
| D5 unfamiliar wording | "mates coming round tonight lol, fancy doing baked salmon, there'll be 6 of us…" | valid, PKR 8,570 of 10,000 |
| D6 infeasible request | "Plan baked salmon for 6 people under 500 rupees" | proven infeasible, suggested budget PKR 8,570 |

- **All six demo cases work** (`demo_cases.json`, `cases_working: 6`). The E0 baseline
  parser gives the same statuses, baskets and totals; the only difference is that
  DistilBERT's dish question also lists the suggestions.
- **Latency** (`app_latency.json`; Windows 10, 4 CPUs, Python 3.11.9, DistilBERT):
  - cold load **27.4 s**, from process start through imports, the catalog, the parser,
    the MiniLM index and the first page;
  - warm request (submit a message: parse, select, validate, explain and re-render)
    p50 **0.19 s**, p95 **0.59 s**, max 0.92 s, over 18 submissions;
  - selection alone p95 0.07 s.

  The warm p95 is far below the 5 s target. The cold load is dominated by loading
  PyTorch and the two models once.
- `run_demo_cases.py --check` and all ten earlier `--check` scripts pass. `pytest`:
  **241 passed, 95 subtests** (230 before, plus 11 in `test_app.py`).
- The new tests are in `tests/unit/test_app.py` (11). They cover:
  - the banner and the status labels for every solver status, and the parser fallback;
  - edits with "what changed" (including the infeasible case), recipe confirmation for a
    broad goal, and the CSV and JSON exports;
  - all six demo cases working, demo texts not taken from benchmark files, and the demo
    record rebuilding with its own parser;
  - `app.py` driven headless: banner, history user, basket table, metrics, two download
    buttons, budget edit → proven infeasible → "use the suggested budget" → valid; a
    clarification answer; recipe confirmation; and a revision in words ("Servings
    changed").
- **Completion check:** all six demo cases work, and cold-load and warm latency are
  measured.

**Findings to carry into the report**

- **The interface adds no logic of its own.** Every number it shows comes from the
  validator or the solver log, and every explanation from verified records, which keeps
  the demo honest.
- **Interactive use is fast once warm** (p95 0.59 s on a 4-CPU laptop). The cost is a
  cold start of about half a minute, mostly loading PyTorch, DistilBERT and MiniLM.
- In D2 and D6 the interface states the proven minimum budget and changes nothing until
  the user accepts it.

**Open limitations**

- **The demo cases are six hand-written conversations, not a user study.** The parser's
  robustness on real user text is measured in Phase 11 on the held-out test templates,
  and it remains a known risk (`docs/nlu_failures.md`).
- **The history user only changes "what I understood".** The history and pair terms
  cannot change product selection (Phase 8).
- The app runs locally for one user; there is no deployment or authentication.
- Latency was measured headless with `AppTest`. A browser adds rendering time that is
  not included.

## Phase 9 — D7 constrained solver and validator (complete, 2026-11-28)

**What changed**

- **`src/smartcart/optimization/cpsat.py`**, the plan's six steps:
  1. Resolve the request: scale, aggregate, subtract the pantry (`resolve_requirements`).
  2. Build the candidate pool from frozen MiniLM retrieval, using the canonical
     ingredient name, the Phase 7 product text and **top 40** (`candidate_count.selected`).
     Hard rules then decide which candidates are options: same ingredient and unit,
     available, every diet `"allowed"`, not excluded. They never enter the objective.
  3. Compute the minimum whole packs and integer option costs.
  4. Build the CP-SAT model:
     - one Boolean per option and exactly one per line;
     - `Σ cost ≤ budget_minor`;
     - an integer objective: relevance + history + pair bonuses (pairs through AND-linked
       Booleans `y ≤ xa, y ≤ xb`) minus cost and surplus penalties, each normalised to
       [0, 1] and scaled by 10^6;
     - main coefficients multiplied by 10^4 with a tie-break (cheaper option, then
       product ID) below them, so the optimum is unique and reproducible.
     A pair of lines whose option pairs all score the same is added as a constant, with
     no variables.
  5. Statuses: `valid`, `needs_clarification`, `no_basket_in_candidate_pool` (logged, then
     the model is rebuilt over every eligible catalog product and solved again),
     `infeasible_in_scope` (proven: no eligible product, or the full-catalog model is
     infeasible), `solver_timeout` (never infeasible), `unsupported` and
     `invalid_request`. Each solve logs the CP-SAT status, the time limit and whether
     optimality was proven.
  6. Validate with the Phase 5 validator: a basket is labelled `valid` only if it passes.

  **Budget conflicts:** the minimum-cost complete basket under the same rules is solved
  and its total is reported as `suggested_budget_minor`; the request is never relaxed.
  CP-SAT runs single-threaded with seed 0 and a 10 s limit.
- **`src/smartcart/explanations/`:** sentences filled only from verified records:
  - per line: packs × product = amount bought vs need, surplus and cost; "cheapest of n
    eligible options" (checked) or why a dearer option was chosen; diet labels;
  - pantry and excluded lines, the total vs the budget, and the simulated-price note;
  - a proven infeasibility with the suggested budget or the missing ingredient;
  - a timeout stated as not proof.
- **`src/smartcart/pipeline/constrained.py`:** the scenario runner. It uses E0's dialogue
  (at most 3 clarification turns, the simulated user answers once) and scores like E0,
  except that only `infeasible_in_scope` counts as detecting an infeasible scenario.
- **`configs/solver.json`** (frozen): candidates, eligibility, constraints, objective
  terms, scaling and weights, solver settings, statuses, and the selection rule (written
  before any dev run).
- **`scripts/run_solver.py [--select|--check]`:** dev basket scenarios with gold input.
  It writes `results/metrics/solver_dev.json`,
  `results/predictions/solver_dev_gold_input.jsonl` (basket, statuses, solver log,
  trace and explanation per scenario) and `results/metrics/solver_latency_dev.json`
  (machine-dependent, not part of `--check`).

**Weight selection (dev, gold input; rule fixed in advance)**

- Fixed: relevance 1.0, history 0.1, pair 0.1. The last two are inactive by Phase 8's
  measurement.
- Tuned: cost {0.25, 0.5, 1, 2, 4} × surplus {0, 0.1, 0.25, 0.5}.
- **All 20 settings tie:** 50/50 success, cost ratio 1.000 to the checker minimum, and the
  same surplus. The rule's last tie-break picked the first entry (**cost 0.25, surplus 0**).
- **On this benchmark the objective reduces to "cheapest eligible option per line"**:
  - products of one ingredient share the same display text, so they have equal relevance;
  - the history and pair terms are constant across products;
  - the cheapest pack is never beaten on surplus by a weight in the grid.

  222 of 222 bought lines are the cheapest eligible option.

**Verification evidence (50 dev scenarios, gold input)**

| Metric | CP-SAT (E3 selector) | E0 |
| --- | --- | --- |
| Success, all scenarios | **50 / 50** | 48 / 50 |
| Valid complete success, feasible (30) | **30 / 30** | 29 / 30 |
| Infeasible detected (10) | 10 / 10 (proven) | 10 / 10 |
| Clarification scenarios (10) | **10 / 10** | 9 / 10 |
| Violations among outputs labelled valid | 0 / 40 | 0 / 38 |
| False rejections / solver timeouts | 0 / 0 | — |

- **Valid baskets:** optimality was proven for 40 of 40, and mean feasible coverage is 1.000.
- **Infeasible scenarios:** 6 have the reason "budget below the minimum cost" and 4 "no
  eligible option" (diet conflicts). All 10 were expanded to the whole catalog to prove
  infeasibility. No feasible scenario needed expansion, so the top-40 pool always held
  an optimal basket. `pair_variables` = 0 (every line pair scored the same).
- **E0's two dev failures are fixed:** dev_b014 (nut-free) and dev_b042 (vegetarian), where
  E0's post-hoc filter dropped an `unknown` cheapest product. As Phase 5 predicted, the
  E0–E3 gap on dev comes only from diet scenarios.
- **Agreement with the Phase 4 checker (exact enumeration):** labels 50/50, minimum
  complete-basket cost 50/50, and suggested budget equal to the checker minimum in 6/6
  budget conflicts. The tests add the plan's small cases and 12 recipes × 3 diets.
- **Latency** (`solver_latency_dev.json`): selection takes a few milliseconds per request
  (CP-SAT about 1–2 ms), far below the 5 s target. Parsing is measured in Phase 11.
- **Completion check:**
  - CP-SAT agrees with enumeration on every small case;
  - the validator rejects deliberately corrupted solver baskets (missing line, duplicate,
    unknown product, zero packs, wrong line cost, unrequested and unavailable products,
    over budget, too few packs);
  - the weights and constraints are recorded in `configs/solver.json`.
- **On the team's Windows machine:**
  - `run_solver.py --check` and all nine earlier `--check` scripts pass;
  - `pytest`: **230 passed, 95 subtests** (209 before, plus 21 in `test_solver.py`).
- **Cross-platform check:** the outputs were first generated on Linux. On Windows, 4 of the
  50 prediction rows differed only in a MiniLM relevance score (1e-6). All 50 baskets and
  statuses, and every metric, were identical. The committed predictions and latency file
  come from Windows (p95 selection 0.017 s, CP-SAT 0.0014 s).
- The new tests are in `tests/unit/test_solver.py` (21). They cover:
  - the small cases against enumeration: worked example, exact budget and one below with
    the suggested budget, multi-pack, excluded ingredient, unknown label, unavailable
    product, pantry covers all;
  - minimum cost on real recipes;
  - the timeout (time limit 0 → `solver_timeout`, never infeasible);
  - every request status, pool expansion and `no_basket_in_candidate_pool`, and the
    infeasibility proof over the whole catalog;
  - AND-linked pair variables changing the choice, and the constant shortcut;
  - hard rules outside the objective (a huge history bonus cannot buy an `unknown` product);
  - a unique reproducible optimum, the validator gate, and explanations;
  - the frozen weights re-derived from the committed grid;
  - dev-only reading and the rebuild check.

**Findings to carry into the report**

- **Constrained selection fixes exactly the failures it should.** On dev, CP-SAT turns
  E0's two diet failures into valid baskets and proves every infeasible case. The gain is
  small because selection is separable here (Phase 5).
- **The objective weights do not matter on this benchmark.** Every grid setting gives the
  same baskets. The objective's terms are implemented and logged, but under the current
  catalog and ingredient-level associations they cannot change a choice. E3 and E4 will
  select the same baskets.
- **Infeasibility is proven, not guessed:** over every eligible catalog product, with the
  required budget reported. A timeout is a separate status.

**Open limitations**

- **Dev only.** `basket_test.json` (200 scenarios) is run once in Phase 11, with the
  parsers end to end and component-isolated.
- **The tie in the weight grid means the chosen weights are not "tuned" in any meaningful
  sense.** Report the tie rather than the weights.
- The top-40 pool is generous for canonical ingredient queries (Phase 7). Expansion is
  used only to prove infeasibility.
- Explanations are templated sentences. They are checked for content in tests, but not
  evaluated with users.

## Phase 8 — D6 associations and Track B (complete, 2026-11-28)

**What changed**

- **Package `src/smartcart/associations/`:**
  - `transactions.py`: ingredient-level Track B transactions. Each order becomes the set
    of catalog ingredients its products map to (Phase 3 mapping). Only the requested
    splits are read; test-order rows are skipped while streaming.
  - `mining.py`: FP-Growth (`mlxtend`) at the grid's lowest count, rules with exact integer
    counts, and the pair table. The bounded pair score is `1 − 1/lift` (lift > 1 and the
    thresholds passed, else 0); it is symmetric and in [0, 1].
  - `trackb.py`: three rankers over the same 118 ingredients and list length 10 (ties by
    popularity, then ID): popularity, personal frequency [S9], and frequency + weight ×
    association term. Also Recall@10 and NDCG@10 overall and for repeat and new items,
    the hash-based tune/report user halves, and a paired bootstrap.
  - `activity.py`: measures whether the pair and history terms can change product
    selection on basket scenarios.
  - `api.py` (BUILD_PHASES 4.3): `pair_score(a, b)`, `basket_pair_score(items)` (a mean,
    never an unbounded sum) and `history_score(user_id, item)`. Products resolve to their
    ingredient. Unknown users, items and same-ingredient pairs score 0.
- **Why ingredient level:** no catalog product has a verified Instacart ID (catalog
  products are simulated), so the plan's fallback applies. 119,846 of 163,626 training
  orders (73%) contain a mapped ingredient.
- **`configs/associations.json`** (frozen), with the selection rule written before any
  validation result was computed:
  - the grid: min count {10, 25, 50, 100, 200} × min confidence {0, 0.05, 0.1, 0.2} ×
    weight {0.1, 0.25, 0.5, 1, 2};
  - tuning on the "tune" half of the validation users, reporting on the "report" half.
- **`scripts/evaluate_trackb.py [--select|--check]`:** mines on training orders, runs the
  grid on the tune half, freezes the choice and stops if it changes. It writes
  `results/metrics/trackb_validation.json` and figure `13_trackb_validation.png`. Per-user
  lists go to the ignored `data/interim/trackb/`, because they are derived from basket
  contents, which are not redistributed (Phase 3 policy).
- **`scripts/mine_rules.py [--check]`:** writes `data/processed/rules.csv` (antecedent,
  consequent, length, count, support, confidence, lift, under the frozen thresholds),
  `results/metrics/association_rules.json`, `association_selection_activity.json` and
  figure `12_association_rules.png`. Time and memory go to
  `association_mining_profile.json`, which is machine-dependent and not part of `--check`.
- **`docs/association_analysis.md`:** the descriptive plots, the strongest rules read by
  hand, helpful and misleading associations, the Track B results, and whether the score
  is active.

**Selection (tune half, rule fixed in advance)**

- Selected: **min count 200, min confidence 0.2, weight 0.1**. This leaves 138 ingredient
  pairs with a positive score; `rules.csv` holds 777 rules (280 directional pairs, 497
  triples).
- **All 100 grid settings score below plain personal frequency on the tune half.** The
  best reaches NDCG@10 0.577, against 0.586 for frequency, so the rule picked the mildest
  setting.

**Verification evidence (validation orders, report half, 3,670 users)**

| Ranker | Recall@10 | NDCG@10 | Repeat R@10 | New R@10 |
| --- | --- | --- | --- | --- |
| Popularity | 0.498 | 0.363 | 0.572 | **0.270** |
| Personal frequency | **0.701** | **0.584** | **0.906** | 0.122 |
| Frequency + association | 0.684 | 0.573 | 0.898 | 0.089 |

- **Users:** 10,000 sampled. 2,661 are excluded because their validation order has no
  mapped ingredient, so recall is undefined. 7,339 are evaluated: 3,669 tune and 3,670
  report.
- **Paired bootstrap** (2,000 resamples, report half):
  - association − frequency: NDCG@10 −0.010 [−0.013, −0.008], Recall@10 −0.017
    [−0.022, −0.012];
  - frequency − popularity: NDCG@10 +0.221 [+0.211, +0.231].
- **Selection activity** (50 dev basket scenarios):
  - the pair term is non-zero in 22 of the 49 multi-line scenarios but **varies with the
    chosen products in 0**;
  - the history term is non-zero for 9 of the 10 history users but **varies in 0**.
- **Mining profile** (`association_mining_profile.json`, Windows machine): `max_len=3` at
  count 10 gives 21,247 itemsets and 112,692 rules in 6.5 s, with peak RSS 295 MB.
- **Completion check:**
  - the rules come from training orders only, tested: every exported pair count equals
    its training-order count, and the validation orders would change it;
  - the Track B metrics file exists;
  - `association_analysis.md` states that the score is **inactive** for selection.
- **On the team's Windows machine:**
  - the Linux-made outputs of `mine_rules.py` and `evaluate_trackb.py` reproduced byte for
    byte, before and after regenerating them there;
  - all seven earlier `--check` scripts still pass;
  - `pytest`: **209 passed, 95 subtests** (186 before, plus 23 in `test_associations.py`).
- The new tests are in `tests/unit/test_associations.py` (23). They cover:
  - FP-Growth counts against brute force;
  - pair-table confidences and lift, and the threshold filters;
  - the bounded lift transform, and both directions of a passing pair exported;
  - manifest split filtering, and no test-order reads;
  - training-only rule counts (with a discriminating check);
  - the `pair_score` contract (symmetry, bounds, unknown and same-ingredient items,
    products through their ingredient, agreement with `rules.csv`);
  - `basket_pair_score` as a bounded mean, and the `history_score` contract;
  - the metric definitions, the tie order and the association term;
  - the deterministic, balanced user halves, and the bootstrap;
  - the frozen choice re-derived from the committed grid, and equal user counts per ranker;
  - the activity measure detecting a synthetic brand-level score, and the committed
    "inactive" result;
  - both rebuild checks.

  The checks that need `data/interim/instacart/` skip on a clone without it.

**Findings to carry into the report**

- **Personal frequency is the strong baseline** [S9]: +0.22 NDCG@10 over popularity, and
  91% of repeat items in the top 10.
- **Associations make Track B ranking worse.**
  - The loss is small but clear, and its bootstrap interval excludes zero.
  - Even at weight 0.1 the term reorders the popularity fill for 3,405 of 3,670 users. It
    promotes niche complements of the user's history (heavy cream, white flour,
    buttermilk, ricotta) over popular staples (almond milk, cucumber, egg, butter). 130
    users gain a hit and 262 lose one.
  - New-item recall falls too (0.089 vs 0.122). This is a null result for the
    association idea.
- **The association score is inactive for basket selection.** With ingredient-level rules,
  every product of an ingredient scores the same, and the selector picks one product per
  fixed line, so both terms add a constant. E4 will select the same baskets as E3, and A3
  the same as E4. Phase 11 should present this as an analysis result.
- **The strongest rules mix complements and substitutes.**
  - Complements: cilantro + lime, garlic + onion, butter + flour, mozzarella + ricotta.
  - Substitutes bought together when stocking up: black beans + pinto beans (the top pair
    by lift), beef broth + chicken broth. A "goes well with" bonus would be wrong for these.
  - Pairs ranked by count (milk + egg) only reflect popularity; the lift-based score
    discounts them.
- The baskets are US Instacart shopping (almond milk is in about 10% of orders), applied
  to a simulated PKR catalog.

**Open limitations**

- **The Track B test orders were not evaluated.** BUILD_PHASES asks for results "on the
  held-out final orders"; following CLAUDE.md, these are evaluated once in Phase 11 with
  `configs/associations.json` frozen. For a test order, the history is the training plus
  validation orders, and the rules stay training-only. The owner can ask for it earlier.
- The report half is held out from tuning but comes from the same validation orders. It
  is not a test result.
- Ingredient-level aggregation through a mapping with 89% precision; only 21% of sampled
  item rows map to a catalog ingredient.
- The rule review in `association_analysis.md` was done by the build agent, not
  independently.

## Phase 7 — D5 semantic retrieval (complete, 2026-11-28)

**What changed**

- **Diet-filter fix** (`retrieval/filtering.py`): a diet is satisfied only by the catalog
  value `"allowed"`. The old `is True` check let no catalog product pass a diet (found in
  Phase 2). `unknown` and `disallowed` still fail.
- **Product text** (`retrieval/product_text.py`), the same for both retrievers:
  - `display_name`: the product name without `SIMULATED`, the house brand ("SmartCart
    Basics/Select/Organic") and the pack size ("parmesan cheese grated");
  - `display_name_ingredient`: `display_name` plus the `ingredient_id` words;
  - `display_name_aliases` (**diagnostic only, never selectable**): adds the reviewed
    aliases. The queries and the aliases share an author, and 14 of the 50 dev queries are
    literal aliases ("dhania", "courgette", "turkey mince"), so this variant measures the
    alias list rather than the retriever;
  - `legacy`: the Phase 1 text, `name` + ingredient words, kept for E0.
- **MiniLM index** (`retrieval/index.py`): frozen `all-MiniLM-L6-v2`, pinned to revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Products are encoded once in catalog order
  (batch 64), L2-normalized, and stored in an exact `faiss.IndexFlatIP`, so scores are cosine
  similarities. A query is always encoded alone, so the API and the benchmark see the same
  vector. The reported score is `(1 + cosine) / 2` in [0, 1].
- **Ranking:** both methods score the whole catalog, round to 6 decimals, then break ties
  by product ID, so float noise cannot reorder near-ties. E0 keeps the Phase 1 raw-float
  order (see the findings).
- **API** (`retrieval/api.py`):
  - `retrieve_candidates(..., method="minilm")` now works;
  - a `product_text` argument, defaulting to the frozen Phase 7 choice
    (`DEFAULT_PRODUCT_TEXT`, tested against the config);
  - `search_products(text, ...)` ranks the catalog for free text (the benchmark).
  - **E0 pins `product_text="legacy"`** (`pipeline/e0.py`), so the committed Phase 5
    results still rebuild byte for byte. Phase 11 re-runs E0 with the Phase 7 text.
- **`scripts/build_index.py [--check]`:** builds the MiniLM index for the frozen text,
  caches it in the git-ignored `models/retrieval/` with the SHA-256 of its inputs (model,
  revision, batch size, product IDs and texts), and writes the committed manifest
  `results/metrics/retrieval_index.json`. The API reads the cache only when the hash
  matches; otherwise it builds the index in memory. `--check` compares the manifest and,
  if present, the local cache.
- **`scripts/evaluate_retrieval.py [--select|--check]`** with the frozen
  `configs/retrieval.json`:
  - scores every product-text variant with both methods on `retrieval_dev.json`;
  - applies the selection rules (written in the config before any dev result existed);
  - stops if the choice differs from the frozen config;
  - writes `results/metrics/retrieval_dev.json`,
    `results/predictions/retrieval_dev_{tfidf,minilm}.jsonl` and
    `results/predictions/retrieval_benchmark_results.json` (replacing the provisional
    pilot numbers), and regenerates figure `11_retrieval_tfidf_vs_minilm.png`.
- **Benchmark scoring** (`retrieval/benchmark.py`): the whole catalog is ranked from the
  query text, then only request-side constraints are applied (required unit, dietary
  rules, availability). The gold ingredient defines relevance only and never reaches the
  filter. Recall@5, Recall@10, and MRR over the top 10.

**Selection (dev only, rules fixed in advance)**

- **Product text:** highest dev Recall@10 averaged over both methods, then averaged MRR.

  | Variant | TF-IDF R@10 / MRR | MiniLM R@10 / MRR |
  | --- | --- | --- |
  | `display_name` | 0.482 / 0.404 | 0.684 / 0.636 |
  | **`display_name_ingredient`** (selected) | 0.486 / 0.437 | 0.680 / 0.585 |
  | `legacy` (diagnostic) | 0.485 / 0.422 | 0.680 / 0.610 |
  | `display_name_aliases` (diagnostic) | 0.800 / 0.757 | 0.877 / 0.847 |

  `display_name_ingredient` wins by **0.0002** in averaged Recall@10 (0.58283 vs 0.58267),
  which is effectively a tie. `display_name` has the better MRR for both methods. The rule
  was followed as written.
- **Candidate count:** the smallest k in {5, 10, 15, 20, 25, 30, 40, 50} whose MiniLM dev
  Recall@k is within 0.01 of Recall@50 gives **k = 40** (Recall@k 0.585 at 5, 0.680 at 10,
  0.740 at 20, 0.820 at 40 and 50). Phase 9 retrieves this many candidates per ingredient
  before the eligibility checks.

**Verification evidence (validation, 50 queries, selected product text)**

| Metric | TF-IDF | MiniLM |
| --- | --- | --- |
| Recall@5 | 0.427 | **0.585** |
| Recall@10 | 0.486 | **0.680** |
| MRR | 0.437 | **0.585** |
| Top-1 product of the right ingredient | 21 / 50 | **28 / 50** |
| Queries with no relevant product in the top 10 | 24 | **16** |

| Query type (n) | TF-IDF R@10 | MiniLM R@10 |
| --- | --- | --- |
| synonym (18) | 0.511 | **0.833** |
| transliteration (10) | 0.000 | 0.000 |
| brand (9) | 0.750 | **0.889** |
| misspelling (7) | 0.333 | **0.857** |
| near-match (5) | **1.000** | 0.800 |
| diet-constrained (1) | 1.000 | 1.000 |

- **Pipeline-pool diagnostic:** with the query `retrieve_candidates` actually uses (the
  canonical ingredient name), the top 10 of both methods holds *every* available product
  of the ingredient for all 35 dev ingredients (32 of 35 at k = 5).
- **Completion check:**
  - dev results exist for both methods;
  - the leak-regression tests pass (the gold ingredient never reaches the filter; a
    wrong-ingredient first result is penalised);
  - the test queries were **not** evaluated (see the open limitations).
- **On the team's Windows machine** (Python 3.11.9, the locked packages):
  - `build_index.py --check`, `evaluate_retrieval.py --check` and all five earlier `--check`
    scripts rebuild byte for byte, so E0, the NLU outputs and the locked benchmarks are
    unchanged;
  - `pytest`: **186 passed, 95 subtests** (164 before, plus 22 in
    `test_semantic_retrieval.py`).
- **Cross-platform check:** the outputs were first generated on Linux. On Windows, 8 of the
  50 MiniLM prediction rows differed only in the sixth decimal of a score (1e-6). Every
  ranking, every metric and the selection were identical. The committed predictions and
  figure 11 were regenerated on Windows.
- The new tests are in `tests/unit/test_semantic_retrieval.py` (22). They cover:
  - the diet fix;
  - product-text normalisation, legacy = Phase 1 text, and aliases not selectable;
  - the MiniLM contract (ranks, score bounds, order, determinism, no hard rules,
    whole-catalog ranking);
  - the ID tie-break;
  - the TF-IDF index equal to the Phase 1 retriever;
  - the cache used only on a matching input hash;
  - the leak regression and the metric definitions;
  - the selection rules, and the frozen choices re-derived from the committed metrics;
  - committed metrics recomputed from the predictions;
  - dev-only reading;
  - both rebuild checks.

  Two older tests changed: the eligibility test now uses `"allowed"`, and "MiniLM waits for
  Phase 7" became "E0 keeps the Phase 1 product text".

**Findings to carry into the report**

- **MiniLM beats TF-IDF on dev** (Recall@10 0.680 vs 0.486, MRR 0.585 vs 0.437). The gain
  comes from synonyms ("courgette", "coriander leaves", "cut up chicken") and misspellings
  ("chiken thighs", "bred crumbs", "eggz"). MiniLM wins 9 queries that TF-IDF misses
  completely, and loses one ("lemon pepper", where green bell pepper ranks first).
- **The 0.90 Recall@10 target is missed on dev** (0.680). It is a target, not a result.
- **Transliterations fail for both methods (0 / 10).** "dhania", "anda", "doodh",
  "namak" and "cheeni" are not English, and the English MiniLM maps them to unrelated
  products (paprika, basmati rice, cheddar). Together with "sweetcorn tin", "polenta",
  "bean curd", "mushrums" and "pace picante sauce", 15 queries fail for both methods.
- **The aliases would fix most of this, but cannot be used fairly here:** with them,
  Recall@10 rises to 0.800 (TF-IDF) and 0.877 (MiniLM). Because the queries and aliases
  were written by the same person, this is reported only as a diagnostic. A real store's
  synonym list, or a multilingual encoder, is future work.
- **Free-text robustness and pipeline retrieval are different questions.** In the pipeline
  the parser maps the user's words to an ingredient ID first, and the query is the
  canonical name. There the top 10 is already complete on dev. The k = 40 chosen by the
  rule is driven by the free-text queries, and costs the Phase 9 solver little.
- **E0's TF-IDF order depends on float noise.** For 4 of 118 canonical queries, distractors
  with scores that are equal in theory (dried basil, thyme, rosemary) come out in
  last-bit float order. E0 keeps that order so Phase 5 reproduces; the Phase 7 ranking
  rounds first and breaks ties by product ID.

**Open limitations**

- **The retrieval test split was not evaluated.** BUILD_PHASES' Phase 7 completion check
  asks for test results. CLAUDE.md and the Phase 6 precedent keep one final look at test
  data, so `retrieval_test.json` is evaluated once in Phase 11 with
  `configs/retrieval.json` frozen. The owner can ask for it earlier.
- **50 dev queries are few:** one query moves Recall@10 by up to 0.02, and the product-text
  choice was decided by 0.0002.
- **Platform:** MiniLM's float results differ slightly between machines (1e-6 between Linux
  and Windows here). Scores are rounded to 6 decimals before ranking, which kept every
  ranking identical, but a `--check` of the prediction file can still report a
  sixth-decimal difference on another platform. The committed files come from Windows.
- **Relevance is at ingredient level** (all house brands of an ingredient count), so the
  benchmark does not test choosing between products of the same ingredient.
- The old `retrieval/semantic.py`, `runner.py` and `queries.py` (pilot generator) are
  superseded but kept, because the Phase 1 tests import them.

## Phase 6 — D4 transformer parser (complete, 2026-11-26)

**What changed**

- **Base model:** `distilbert/distilbert-base-uncased`, pinned to revision
  `12040accade4e8a0f71eabdb258fecc2e7e948be`. It was downloaded once into the Hugging
  Face cache; the default "xet" download failed, so `HF_HUB_DISABLE_XET=1` was used.
  Training and evaluation run with `HF_HUB_OFFLINE=1`.
- **Training** (`scripts/train_nlu.py`, `src/smartcart/nlu/training.py`):
  - Two models per seed: sequence classification for intent, and token classification
    over 21 BIO tags for slots. Only the first sub-token of each word is labelled.
  - Seeds 13, 42 and 7. Plain PyTorch AdamW with lr 5e-5, batch 16, weight decay 0.01,
    10% linear warm-up, max length 96 (the longest annotation is 50 sub-tokens).
  - 6 epochs for intent and 8 for slots. The epoch with the best dev score is kept.
  - Only the 600 training examples update the weights.
  - Checkpoints are in `models/nlu/transformer/seed<seed>/{intent,slots}/` (git-ignored).
    The per-epoch log is `results/metrics/nlu_training_log.json` (tracked).
  - Training took **about 75 min on CPU** (4 threads), about 2 min per epoch.
- **Parser** (`nlu/transformer_parser.py`, `nlu/normalize.py`):
  - `TransformerParser` reuses E0's normalisation, revision merge, clarification rules,
    answer handling and the same two dialogue-state rules, so the comparison isolates
    the models.
  - `SpanNormalizer` gives tagged spans their values: exact alias, then plural, then a
    close spelling at difflib ratio ≥ 0.85, then attachment. It reproduces all 3,273 gold
    values and attachments in train and dev.
  - Temperature-scaled intent confidence.
  - A runtime `low_confidence_intent` question when the confidence is below the seed's
    threshold.
  - Up to 3 feasible, cheapest-first recipe suggestions when the dish is missing.
  - Unsupported detection through the intent class.
- **API:** `parse_request(..., parser="transformer", seed=None)` uses the primary seed 42
  by default, and `load_transformer_parser()` loads any seed.
- **Calibration and evaluation** (`scripts/evaluate_nlu.py [--calibrate|--check]`):
  - For each seed, fits the temperature on dev NLL and picks the threshold on dev (wrong
    intents caught minus correct intents questioned), then freezes both in
    `configs/nlu_transformer.json`.
  - Evaluates both parsers on dev with the shared `nlu/metrics.py`.
  - Writes `results/metrics/nlu_dev.json` (E0, every seed, mean ± std),
    `results/metrics/nlu_calibration.json` and
    `results/predictions/nlu_dev_transformer_seed{13,42,7}.jsonl`.
- **Figures** regenerated from real outputs: `09_nlu_intent_confusion_matrix.png` (E0
  vs DistilBERT, classifier-only intent, dev) and `10_nlu_training_curves.png` (from the
  training log). `results/figures/README.md` is updated.
- **Shared code:** the E0 parser gained hooks (`extract_spans`, `confidence_gate`,
  `suggest_recipes`). All 7 E0 outputs still rebuild byte-for-byte.
- **Failure review:** `docs/nlu_failures.md` covers all 45 DistilBERT dev failures (28
  reviewed rows, 10 causes), E0's 4 failures, and the decisions taken before freezing.

**Verification evidence (validation, 150 examples; DistilBERT = mean ± std over 3 seeds)**

| Metric | E0 | DistilBERT |
| --- | --- | --- |
| Intent macro-F1, classifier only | 0.837 | **0.943 ± 0.005** |
| Intent macro-F1, with the shared context rules | **0.978** | 0.972 ± 0.016 |
| Slot entity micro-F1 | **0.991** | 0.962 ± 0.010 |
| Quantity attachment | **0.975** | 0.966 ± 0.012 |
| Exact budget (gold set) | **1.000** | 0.978 ± 0.009 |
| Exact servings (gold set) | **1.000** | 0.959 ± 0.032 |
| Clarification type accuracy (15 gold) | 0.800 | **0.844 ± 0.083** |
| Unnecessary clarifications | **0** | 3 ± 0.8 |
| Whole-request exact match | **0.973** | 0.900 ± 0.011 |

- **Per seed:**
  - kept epochs: intent 5 / 2 / 3 (seeds 13 / 42 / 7), slots 4 / 5 / 5;
  - dev slot F1 at the kept epoch: 0.954 / 0.956 / 0.976.
- **Calibration:**
  - temperatures 1.10 / 1.25 / 1.35, all slightly overconfident before scaling;
  - ECE 0.025 → 0.023, 0.048 → 0.022, 0.049 → 0.030;
  - thresholds 0.5 / 0 / 0. Seed 13's rests on one example, and the gate fired once on
    dev, catching a wrong intent.
- **Completion check:**
  - the checkpoints load locally (`parse_request` test);
  - metrics exist for both parsers;
  - figures 09 and 10 are regenerated from logs and predictions;
  - the calibration and thresholds are frozen in `configs/nlu_transformer.json`.
- `evaluate_nlu.py --check`: all 5 outputs rebuild byte-for-byte from the checkpoints.
  `run_baseline.py --check` still passes.
- `pytest`: **164 passed, 95 subtests** (152 before, plus 12 in
  `test_transformer_parser.py`). The new tests cover:
  - BIO repair and decoding, first-sub-token labelling, and every annotation fitting
    `max_length`;
  - the normaliser on all gold spans, plus misspellings and unknown words;
  - temperature fitting, ECE and the threshold rule;
  - recipe suggestions;
  - training-log consistency (epoch counts, kept epoch = best dev);
  - the transformer `parse_request` with a revision;
  - committed metrics recomputed from predictions, and frozen calibration plus rebuild.

  The checkpoint tests skip on a clone without `models/`.

**Findings to carry into the report**

- **DistilBERT wins on intent alone (+0.106 macro-F1).** The rules close that gap, and
  the E0 dictionaries win on slots.
- **Why the slots go the other way:** most transformer errors (31 of 45) involve
  validation-only phrasing ("6 portions", "I have X left", "found X in the fridge",
  "throw in X", "can we do it for X instead"). The dictionaries key on catalog words
  that every split shares. This is the template-data bias already noted in Phase 4,
  measured. Expect the same on test, which also uses held-out templates.
- **Clause punctuation matters.** In a hand-written probe without commas, 2 of 3 seeds
  read "for 2 under 1500 rupees" as a 2-rupee budget.
- The low-confidence gate contributes almost nothing on this data: the confidence of
  wrong intents is mostly high (0.95+ for the list/plan errors).

**Open limitations**

- **The test split was not evaluated in Phase 6.** BUILD_PHASES says to evaluate test
  "once frozen". To keep a single, final look at the test data, the NLU test metrics for
  both parsers are produced once in Phase 11 with the frozen configs, alongside every
  other test-set result. The owner can ask for them earlier.
- **Retraining is seeded, but byte-identical retraining is not verified.** CPU kernels
  and thread counts can change the last digits. The committed predictions and metrics
  are reproduced exactly from the trained checkpoints (`--check`).
- **Teammates need the checkpoints to run the transformer:** about 75 min of CPU
  training, or a copy of `models/nlu/transformer/` (1.5 GB, not in git).
- Results come from template-generated text (see Phase 4). Absolute scores are likely
  optimistic for both parsers, and the ranking between them may not transfer to real
  user text.
- The old `nlu/transformer_model.py` (random-weight skeleton), `nlu/runner.py` and
  `results/predictions/nlu_evaluation_results.json` are superseded but kept, because
  older tests import them.

## Phase 5 — D3 complete baseline E0 (complete, 2026-11-26)

**What changed**

- **Baseline parser** (`src/smartcart/nlu/baseline_parser.py`, `lexicon.py`):
  - **Intent:** a scikit-learn `Pipeline` of `TfidfVectorizer` and `LinearSVC`, trained
    only on the 600 training examples. The rows are checked against `nlu_split.json`.
  - **Slots** cover all 10 types:
    - longest-match gazetteers over catalog ingredient names and reviewed aliases (plus
      simple plural variants), the 89 recipe aliases, and diet words;
    - number rules: digits, `1,350`, `1.5k`, `3550/-`, word numbers such as
      "twenty-five hundred", and "a dozen";
    - unit words, converted with the NIST factors;
    - currency words.
  - **Roles:** a number followed by a unit or an ingredient is a QUANTITY attached to that
    ingredient. A number next to a currency word, with a `k` or `/-` suffix, or of at
    least 100 is a BUDGET. Any other integer up to 30 is SERVINGS.
  - **Negation and pantry:** a negation cue before an ingredient in its clause makes an
    EXCLUSION on the ingredient only. Negated diet categories ("no dairy") are matched
    first as DIET spans. Pantry cues ("have", "got", "pantry", "left", "fridge" …) make a
    PANTRY item.
  - **Normalisation** to a StructuredRequest: amounts in catalog units, budgets in minor
    units, revisions merged into `session`. Rule-based clarification covers all 5 gold
    types, and `answer()` applies a user's reply to the pending question.
  - **Two dialogue-state rules** sit on top of the classifier, and both are reported:
    `revise_basket` needs a session, and with a session a request that names no meal is
    read as a revision. E0 has no confidence gating.
- **`parse_request(..., parser="baseline")`** (`nlu/api.py`); `parser="transformer"`
  raises until Phase 6.
- **`retrieve_candidates(..., method="tfidf")`** (`retrieval/api.py`): ranks the whole
  catalog for one ingredient (query = canonical ingredient name) and returns
  `product_id`, `retrieval_score` in [0, 1] and `rank`. MiniLM raises until Phase 7.
- **E0 selection** (`pipeline/e0.py`):
  - resolve requirements with the gold policy;
  - TF-IDF top 10 per line;
  - the cheapest available product with the right ingredient and unit, chosen per line
    independently;
  - a **post-hoc diet filter** that drops non-`allowed` products, leaving the line uncovered.
  - Statuses: `valid`, `over_budget`, `incomplete`, `no_requirements`,
    `invalid_request`, `needs_clarification`, `unsupported`. Incomplete and invalid
    outcomes count as failures.
- **Independent validator** (`validation/validator.py`): recomputes needs, units,
  availability, diet, exclusions, packs, line costs, duplicates, missing lines and the
  budget from product IDs and pack counts, and reports coverage. Phase 9 reuses it.
- **NLU metrics** (`nlu/metrics.py`): intent (per class plus confusion matrix),
  entity-level slot F1 per label, quantity attachment, exact budget and servings,
  clarification, whole-request exact match. Phase 6 shares them.
- **Runner:** `scripts/run_baseline.py --config configs/experiments/E0.json [--check]`.
  It writes:
  - `results/metrics/E0_intent_tuning.json`, `E0_nlu_dev.json`, `E0_basket_dev.json`
    and `E0_latency_dev.json`;
  - `results/predictions/E0_nlu_dev.jsonl`;
  - `E0_basket_dev_{gold_input,end_to_end}.jsonl`;
  - `E0_reference_baskets.json`.

  The intent model goes to the ignored `models/nlu/E0_intent.joblib`. The runner reads
  no test file and refuses any split other than dev.
- **Config** `configs/experiments/E0.json` (frozen): data paths, the intent model, the
  15-entry tuning grid and its selection rule, TF-IDF top 10, independent selection,
  post-hoc filtering, association weight 0 and at most 3 clarification turns.

**Tuning (validation only)**

- **Intent grid:** word (1–2), char_wb (2–4) and word+char features × C ∈ {0.01, 0.03,
  0.1, 0.3, 1}, trained on train and scored on dev.
  - Selected: **char_wb (2–4), C = 0.1, dev macro-F1 0.837** (word (1–2) at C = 1 gave 0.725).
  - The runner re-runs the grid and stops if the best entry differs from the frozen config.
- **Context rules** were added after reading dev errors: most were dev openers never seen
  in training ("I feel like …", "Thinking of making …") classified as `revise_basket`.
- Retrieval `top_k = 10` was fixed by the plan, not tuned.

**Verification evidence (dev only)**

- **Completion check:**
  - The 5 reference structured requests (pilot catalog) produce itemized baskets equal
    to the hand-calculated lines, totals and statuses: **5/5**.
  - Validation predictions are saved.
  - The E0 configuration is in `configs/experiments/E0.json`.
- **NLU, 150 validation examples:**

  | Metric | Value |
  | --- | --- |
  | Intent macro-F1, classifier only / with context rules | 0.837 / 0.978 |
  | Intent accuracy, classifier only / with context rules | 0.833 / 0.973 |
  | Slot entity micro-F1 (P / R) | 0.991 (1.000 / 0.982) |
  | Quantity attachment | 231/237 = 0.975 |
  | Exact budget / servings (when gold is set) | 108/108, 81/81; no spurious values |
  | Clarification decision (P / R), type accuracy | 15/15 asked, 1.000 / 1.000; type 12/15 |
  | Whole-request exact match | 146/150 = 0.973 |

  - Classifier-only per-class F1: list 0.892, plan 0.826, **revise 0.632**, unsupported 1.000.
  - All remaining errors are intent errors. In 3 lists with an unquantified item, the
    intent was predicted as `plan_meal`; in 1 plan request it was predicted as a list.
- **Basket, 50 `basket_dev` scenarios:**

  | Metric | Gold input | End to end |
  | --- | --- | --- |
  | Valid complete success, feasible (30) | 29 (0.967) | 27 (0.900) |
  | Mean coverage, feasible | 0.993 | 0.926 |
  | Infeasible detected (10) | 10 | 10 |
  | Clarification success within 3 turns (10) | 9 | 8 |
  | Unnecessary clarifications | 0 | 1 |
  | Violations among outputs labelled valid | 0 / 38 | 0 / 35 |
  | Lines dropped by the post-hoc diet filter | 11 | 11 |
  | `has_history` subset success | 9/10 | 9/10 |

  - **Every E0 selection failure comes from the post-hoc diet filter:**
    - `dev_b014` (nut-free): the cheapest water and cheddar are `unknown` for nut-free;
    - `dev_b042` (vegetarian): the cheapest water is `unknown` for vegetarian.
  - The other end-to-end failures are parser intent errors:
    - a meal request read as a list, leaving nothing to buy;
    - two lists read as meal requests, so the parser asked for a dish.
- **Latency on this laptop** (not part of `--check`): cold load 0.30 s; warm p50/p95
  0.040 / 0.063 s end to end.
- `run_baseline.py --check`: all 7 outputs rebuild byte-for-byte.
- `pytest`: **152 passed, 95 subtests** (121 before, plus 18 in `test_baseline_parser.py`
  and 13 in `test_e0_pipeline.py`). The new tests cover:
  - number and unit forms, attachment, and diet negation vs ingredient exclusion;
  - pantry with and without an amount, budget and currency spans, and alias vs
    ambiguous-diet precedence;
  - all clarification rules, revision merging, the context rules (also turned off), and
    answer handling;
  - training rows only, and frozen config equal to the tuning choice;
  - predictions on dev IDs only, and committed metrics recomputed from predictions;
  - retrieval: whole-catalog ranking, score bounds, no hard rules;
  - selection: E0 equals the checker minimum on every feasible dev request without a
    diet; the post-hoc filter; the statuses;
  - the validator rejecting 10 kinds of corrupted basket;
  - the rebuild check.

**Findings to carry into the report**

- **Selection is separable in this benchmark.** Line costs add up, and each line takes one
  product. So whenever no diet applies, the per-line cheapest choice *is* the minimum-cost
  basket. A test confirms it on every such dev request. E0 loses only through the
  post-hoc diet filter (an `unknown` cheapest product), the candidate pool, or parsing.
  Constrained selection (E3) can therefore only gain on diet scenarios and on the
  objective terms, so the E0–E3 gap is expected to be small and concentrated there.
- **Infeasible detection is 10/10 only because pool and minimum coincide here.** E0
  cannot tell "proven infeasible" from "my heuristic failed". On dev the TF-IDF top 10
  always held a compatible product (0 lines without one), so its `over_budget` matched
  the true minimum.
- **TF-IDF per-ingredient retrieval is nearly trivial.** The product text includes the
  ingredient's name words (unchanged since Phase 1). Phase 7 decides the product text
  for both retrievers, and E0 is re-run in Phase 11 with the same text.

**Open limitations**

- **The slot scores are optimistic.** Template text uses catalog aliases and recipe
  aliases, and the baseline's dictionaries are exactly those lists. The report must state it.
- **The context rules make revision detection almost free.** In the NLU data only
  revision examples carry a session. The classifier-only intent scores are reported next
  to the final ones for that reason.
- **Possible test leakage of the rule author's knowledge.** The cue word lists were
  written from training and validation examples plus common words. The rule author (the
  build agent) had read the generator source, which contains the test templates, but no
  test example was parsed or scored. Disclose this in the report.
- E0 has no confidence gating; low-confidence clarification is a Phase 6 feature.
- The simulated user answers one question once. A second question in the same scenario
  goes unanswered, so the "3 turns" limit is not exercised on dev.
- The old keyword parser (`nlu/parser.py`, `nlu/intent.py`, `pipeline/baseline.py`) and
  `nlu/runner.py` remain for the Phase 1 reference tests. They are superseded by E0, and
  `results/predictions/nlu_evaluation_results.json` is still the old 8-example output
  (replaced in Phase 6).

## Phase 4 — D2 benchmarks and gold feasibility checker (complete, 2026-11-25)

**What changed**

- **Gold feasibility checker** (`src/smartcart/validation/feasibility.py`):
  - Resolves the requirements: recipe lines scaled to servings, plus items, aggregated,
    minus pantry, minus excluded ingredients.
  - Builds the eligible options per line: same ingredient and unit, available, every
    diet `"allowed"`; `unknown` fails.
  - Finds the exact minimum-cost basket by depth-first enumeration (pruning only branches
    that cannot beat the best basket).
  - Returns the label (`feasible`, `infeasible`, `clarification` or `unsupported`), the
    reason, the minimum cost and the cheapest basket.
- **Benchmark generator:**
  - `src/smartcart/benchmarks/`:
    - `groups.py`: grouped splits;
    - `language.py`: tokenizer, span builder, units, numbers and budgets;
    - `requests.py`: phrasing pools per split, rendering, gold StructuredRequests;
    - `build.py`: scenario designs and clarification answers.
  - `scripts/build_benchmarks.py`: writes everything, runs 16 checks, and supports
    `--check` (byte-for-byte rebuild plus lock verification) and `--lock`.
  - `configs/benchmarks.json` holds the settings.
- **Hand-written inputs:**
  - `data/processed/recipe_aliases.csv`: 89 user-facing meal names for the 42 recipes,
    including transliterations such as "anda bhurji" and "aloo soup";
  - `configs/retrieval_queries.csv`: 150 retrieval queries.
- **NLU annotations:** `data/annotations/nlu.jsonl`.
  - **900 examples:** 300 seeds × 3 paraphrases. Intents per split: 240/60/60 plan_meal,
    150/36/36 grocery list, 120/30/30 revise, 90/24/24 unsupported.
  - Each example has tokens, BIO tags over the 10 slot labels, character spans with
    normalized values, quantity → item attachment (`attach_to`), the session for
    revisions, and the gold StructuredRequest.
  - Clarification examples cover all 5 gold types in train and test. NLU dev has no
    `missing_recipe` example; the basket dev set has 4.
  - `data/splits/nlu_split.json` gives the 600/150/150 split by `seed_id`.
- **Grouped splits** (`data/splits/benchmark_groups.json`):
  - Whole meal families go to one split: 16 / 8 / 18 recipes. Grocery-list families are
    drawn from each split's recipe ingredients.
  - Phrasing templates are partitioned by split, so dev and test text uses templates never
    seen in training.
- **Basket benchmark:**
  - `data/benchmarks/basket_test.json`: **200 scenarios (120 / 40 / 40)** across 24 test
    families. `basket_dev.json`: 50 scenarios (30 / 10 / 10).
  - The test infeasible scenarios are 25 budget-below-minimum and 15 diet conflicts. Test
    has 26 exact-budget feasible scenarios and 66 with multi-pack lines.
  - Clarification scenarios carry an answer and a resolved request with its own label.
  - 40 test and 10 dev scenarios have an Instacart `user_id` whose Track B training
    history shares at least 2 required ingredients.
- **Retrieval benchmark:** `data/benchmarks/retrieval_{dev,test}.json`.
  - 50 / 100 hand-written queries, with ingredient groups of 40 dev / 78 test that never
    overlap.
  - Query types: synonym, real brand names, misspellings, Urdu transliterations
    (dhania, kali mirch, qeema …), misleading near-matches, and diet-constrained queries.
  - The relevant set is every available product of the target ingredient that is
    `allowed` for the query's diet.
- **Docs:**
  - `docs/benchmark_policy.md`: the basket semantics behind every label, the annotation
    scheme, how the data was generated, the splits and the limitations.
  - `docs/annotation_review.md`: the review record.
  - `docs/benchmark_lock.md`: SHA-256 of the locked files.
  - `BUILD_PHASES.md`: adds the `missing_item_quantity` clarification type; Phase 7 now
    uses the locked retrieval files.

**Contract decisions (documented in `benchmark_policy.md`)**

- **Exclusions drop the ingredient** from the requirements (the user cooks without it),
  and none of its products may be bought. Infeasibility comes from budgets and diets.
- **Budgets are inclusive caps.** Strict wording ("under" or "below") is never generated
  when the budget equals the minimum cost.
- **A request with no budget has no cost limit.** Only vague cost wording triggers
  `missing_budget`.
- **No servings means the recipe's base servings**; the gold `servings` stays `null`.
- **`missing_item_quantity` is a new clarification type.** `low_confidence_intent` is
  runtime-only and never a gold label.
- **"Lactose-free" is not dairy-free.** A negated diet category ("no dairy") is a `DIET`
  span; a negated ingredient is an `EXCLUSION` span on the ingredient only.

**Verification evidence**

- `build_benchmarks.py`: all 16 checks pass (`results/metrics/benchmark_checks.json`).
  They include:
  - the counts;
  - no seed or family overlap;
  - test families absent from dev and from NLU training;
  - no identical text across splits;
  - distinct paraphrases;
  - spans consistent with gold;
  - every basket label reproduced by the checker;
  - the history counts;
  - disjoint retrieval ingredients.
- `build_benchmarks.py --check`: all 8 files rebuild byte-for-byte, and the 5 locked files
  match `docs/benchmark_lock.md`.
- `pytest`: **121 passed, 95 subtests** (92 before, plus 10 in `test_feasibility.py` and
  19 in `test_benchmarks.py`).
  - Checker cases from the plan:
    - the worked example (600 g needed, 200 g pantry, 250 g packs → 2 packs, 100 g surplus);
    - exact budget, and one below it;
    - multi-pack;
    - excluded ingredient;
    - unknown label;
    - disallowed and unavailable products;
    - pantry covers everything;
    - the pruned search equals full enumeration on 12 recipes × 3 diets.
  - Benchmark tests: counts, grouping, label reproduction, test-family isolation,
    required-case coverage, history users from the Phase 3 sample, retrieval relevance
    recomputed, token/BIO/span integrity, the gold contract, the lock, and the rebuild.
- **Annotation review:** the build agent read the 180-example sample twice.
  - Round 1 found 5 gold-label problems (2.8%): "lactose-free" annotated as dairy-free,
    and strict "below" wording on exact budgets. It also found 5 text problems.
  - All were fixed in the generator and verified dataset-wide.
  - Round 2 found no gold errors. It did turn up duplicate paraphrases, which are now
    prevented by a check.

**Open limitations**

- **The text is template-generated**, not written by people, so parser scores on it are
  likely optimistic. Held-out templates reduce, but do not remove, this bias. The report
  must state it.
- **The second-person annotation check is pending.** The build agent wrote the generator,
  so its review is not independent. A teammate should judge the 180 rows in
  `review_sample.jsonl`; otherwise do a delayed self-review and disclose it.
  Any fix means rebuilding and re-locking.
- Number agreement on ingredient nouns is not inflected ("six egg"). This is cosmetic;
  gold labels are unaffected.
- `has_history` users are matched at ingredient level through the Phase 3 mapping (about
  89% precision).
- The old `retrieval/queries.py` generator and `results/predictions/retrieval_benchmark_results.json`
  are superseded and are replaced in Phase 7.

## Phase 3 — D2 transaction sample and Track B splits (complete, 2026-11-25)

**What changed**

- **Code:**
  - `src/smartcart/data/instacart.py`: hash-based user sampling, the Track B split,
    chunked order-product streaming, ordered mapping rules, and review scoring with
    Wilson intervals.
  - `scripts/prepare_transactions.py`: builds everything, profiles time and memory,
    and writes the checks. `--check` verifies reproducibility.
  - `configs/instacart_sample.json`: seed 20261125, 10,000 users, at least 5 usable orders.
- **User sample:** `data/splits/instacart_users.json`.
  - Usable orders are prior or train orders; the 75,000 test orders have no product rows.
  - 175,072 users are eligible; 31,137 are excluded for having 3–4 usable orders.
  - 10,000 users are taken in ascending `sha256(seed:user_id)` order, with no RNG library involved.
- **Track B manifest:** `data/splits/instacart_trackb.json`. For each user the last
  usable order is test, the one before is validation, and the rest are training:
  163,626 / 10,000 / 10,000 orders. Baskets are product sets; cart position and the
  reorder flag are dropped.
- **Ingredient mapping:**
  - `configs/instacart_ingredient_map.csv` holds 119 ordered rules, each with aisles,
    an include pattern and an exclude pattern.
  - `data/processed/instacart_ingredient_map.csv` maps **3,288 Instacart products to
    all 118 catalog ingredients**, covering all 98 recipe ingredients.
  - Mapped products are 21.4% of sampled item rows, and about 74% of sampled orders
    contain one. No catalog product is matched to Instacart, because catalog products
    are simulated.
- **Mapping review** (`data/processed/instacart_mapping_review.csv`): after two
  development rounds the rules were frozen. Held-out results:
  - precision 134/150 = **89.3%** (95% CI 83.4–93.3%);
  - 3/150 unmapped products are misses, which implies about 90% recall within the rule aisles.
- **Redistribution:** Instacart product names and basket contents are not committed.
  The tracked files hold IDs only. A readable mapping and the sampled item rows are
  written to the ignored `data/interim/instacart/`.
- **Docs:** `docs/data_card.md` has a new section with the sampling, split, exclusions,
  mapping policy, coverage and review.

**Verification evidence**

- `prepare_transactions.py`: all 6 checks pass (`results/metrics/transaction_checks.json`).
  Runtime is about 17 s, with process RSS at most 266 MB at the sampled steps. The
  32.4 M prior rows are streamed in 17 chunks.
- `prepare_transactions.py --check`: the user manifest, the Track B manifest and the
  mapping all rebuild byte-for-byte.
- `pytest`: **92 passed, 95 subtests** (76 before, plus 16 in `tests/unit/test_instacart.py`).
  The new tests cover:
  - sampling determinism, order independence and the too-few-users error;
  - split boundaries and test-set exclusion;
  - chunked streaming, de-duplication and dropped columns;
  - rule order, aisle restrictions and near-miss exclusions;
  - Wilson intervals;
  - consistency of the committed manifests (hash, coverage, no order in two splits);
  - the review matching the current mapping;
  - a rebuild from the archive (skipped when the archive is absent).

**Open limitations**

- The mapping review was done by **one reviewer** (the build agent). A teammate should
  re-judge the 300 held-out rows. The 16 known errors and 3 misses are deliberately left
  unfixed; any rule change needs a new held-out review.
- Recall was estimated only in the aisles that rules name, and products are not weighted
  by purchase frequency.
- Some ingredients have very few Instacart products (beef tenderloin and onion salt 1
  each; chicken cutlet and cooked brown rice 3 each), so their history signal will be sparse.
- 31,137 users with fewer than 5 usable orders are outside the sample by design.

## Phase 2 — D2 full catalog and recipes (complete, 2026-11-25)

**What changed**

- **New catalog** `data/processed/catalog.json`, built by `scripts/prepare_data.py` from
  reviewed inputs:
  - `data/processed/recipes.csv`
  - `data/processed/recipe_lines.csv`
  - `data/processed/ingredients.csv`
  - `data/processed/synonyms.csv`
  - `configs/catalog_build.json`

  The pilot catalog is unchanged, and all 20 pilot products and 3 pilot recipes carry
  over into the full catalog unchanged.
- **Recipes: 42 across 27 meal families.**
  - Food.com candidates were filtered for structure and popularity, with pork and
    alcohol excluded (a reversible design choice for the PKR context).
  - **51 recipe pages were checked on food.com:** 39 accepted, 12 rejected for lines
    that could not be converted without inventing amounts.
  - Units come from the pages, because the dataset has none and its quantity lists are
    misaligned for "X or Y" lines. Servings come from the dataset.
- **Ingredients:** 118 canonical ingredients (98 used in recipes, 20 distractors for
  retrieval near-misses) with **167 reviewed aliases**. These include British and
  Urdu-transliteration aliases such as dahi, aloo, pyaz, chanay and atta.
- **Products: 466 simulated options.**
  - Fictional house brands (Basics, Select, Organic), several pack sizes per ingredient,
    PKR prices in minor units.
  - 12 dietary variants: vegetarian cheddar, gluten-free tamari, vegan mayonnaise and others.
  - 4 deterministic unavailable products.
- **Conversions:** NIST lb, oz, cup, tbsp and tsp, plus 24 ingredient-specific
  King Arthur weight-chart estimates. The project policy for dash and pinch is documented.
- **Code:**
  - `validate_catalog()` and `load_catalog()` in `data/contracts.py` (pilot contract plus `meal_family`);
  - `data/catalog_build.py` (deterministic build);
  - `data/catalog_checks.py` (coverage, duplicate, missing-field and target checks);
  - `scripts/prepare_data.py` (`--check` verifies the catalog is reproducible).
- **Docs:**
  - `docs/data_card.md`: sources and terms, selection, the full line-resolution policy,
    the simulation and dietary policies, and known gaps.
  - `BUILD_PHASES.md`: corrected the dietary-value wording to `allowed` / `disallowed` / `unknown`.

**Verification evidence**

- `scripts/prepare_data.py`: all checks pass. The results are in `results/metrics/catalog_checks.json`:
  - recipes ≥ 38, meal families ≥ 20, products within 300–500;
  - every recipe line is covered by an available product;
  - no duplicate product names and no missing fields.
- `prepare_data.py --check`: the committed catalog rebuilds byte-for-byte.
- `pytest`: **76 passed, 95 subtests** (63 before, plus 13 catalog tests). The new tests cover:
  - reproducibility and the scope targets;
  - pilot preservation and line coverage;
  - exact converted amounts (2 cups cheddar = 226 g; 16 oz = 453.593 g; 1 bunch = 6 stalks; 2 pinches = 0.617 ml);
  - serving scaling;
  - distractors, dietary variants and labels;
  - Basics availability and simulation labelling;
  - the meal-family contract;
  - the price helper.
- The cheapest complete basket at base servings ranges from PKR 500 (pasta dough) to
  PKR 9,990 (4 lb beef tenderloin). Every recipe is purchasable.

**Open limitations**

- **Independent review is pending** for all 42 recipes and for the `agent_reviewed`
  ingredient mappings. A teammate should spot-check lines against the pages.
- Lines were checked against fetched page text; servings are from the dataset.
- There is no stew or stir-fry family: those candidates needed volume-to-mass conversions
  for chopped vegetables, which no cited source covers.
- Spices, condiments and purées are stocked by volume, a simulation simplification.
- **Bug found for Phase 7:** `retrieval/filtering.py` checks dietary values with `is True`,
  but the catalog uses `"allowed"`, so no product can pass a dietary filter.
- Pilot products keep all-`unknown` dietary labels, so they never satisfy a hard diet request.

## Phase 0 — Repo prep, raw data, D1 scope (complete, 2026-11-25)

Phase 1 was done first, at the owner's request.

**What changed**

- **Raw data restored.** `data/raw/archive_3.zip` (Instacart) and `data/raw/archive_4.zip`
  (Food.com) are back in place. Their SHA-256 hashes match the original audit exactly:
  `c347cd7f…3038` and `fa7910c9…527d`.
- **Audit re-run.** `scripts/audit_data.py` took 243 s and regenerated
  `docs/data_audit.md`, `data/interim/audit/summary.json` and `recipe_candidates.csv`.
- **`.gitignore`** now tracks `data/processed/catalog.json`, `data/annotations/*.jsonl`,
  `data/benchmarks/*.json`, `data/splits/*.json`, `results/metrics/` and
  `results/run_manifest.json`. Raw archives, audit intermediates and `models/` stay ignored.
- **D1 scope.** Added `docs/scope.md`: user scenario, pipeline, core and out-of-scope items,
  the simulated-price policy, contribution statement, RQ1–RQ3, definition of success,
  Tracks A and B, and the unresolved 90% rubric note.
- **Literature skeleton.** Added `docs/literature/review.md`: the 15-row comparison table
  with the six closest papers from the plan [S7]–[S12] pre-listed (analysis cells empty
  until each paper is read), completion rules and the synthesis outline.

**Verification evidence**

- The regenerated `docs/data_audit.md` is identical to the committed version except for
  the `Generated:` timestamp. Every count, hash and check reproduced:
  - Instacart: 49,688 products, 3,421,083 orders, 32,434,489 prior rows and 1,384,617 train rows.
  - Food.com: 522,517 recipes.
- `git check-ignore` confirms the new data and result paths are tracked, and that
  `data/raw/`, `data/interim/` and `models/` remain ignored.
- `pytest`: 63 passed, 95 subtests.

**Open items**

- **External input:** the team's literature-matrix spreadsheet must be added to
  `docs/literature/`. Rows 7–15 and all analysis cells wait on it and on reading the papers (Phase 12).
- The rubric's missing 10% is to be confirmed with the instructor (see `docs/scope.md`).

## Phase 1 — Fix inherited defects (complete, 2026-11-25)

**What changed**

- **D3 pantry bug.** Reference scenario `d3_ref_02` now uses pantry key
  `white_flour` (was `'flour'`, which matched nothing, so pantry stock was ignored).
  The 250 g in the pantry now covers the 120 g requirement, so no flour is bought.
- **D3 basket assembly** (`optimization/basket.py`):
  - A line fully covered by the pantry returns `line_status: covered_by_pantry`, with 0 packs and 0 cost.
  - An ingredient with no compatible product returns `line_status: no_compatible_option`, and the basket status becomes `incomplete`, instead of raising. The uncovered IDs are listed in `uncovered_ingredients`.
  - Every line now carries its `ingredient_id`. `item_count` counts purchased lines only.
- **D3 unmatched pantry keys** (`pipeline/baseline.py`): the basket lists `ignored_pantry_keys`, so a misspelled pantry ingredient is visible instead of silently ignored.
- **D3 evaluator** (`pipeline/evaluator.py`):
  - A scenario passes only if status, maximum cost, the **exact total**, **every expected line** (ingredient, product, packs, line cost) and pantry use all match.
  - All 5 reference scenarios now carry hand-calculated expected lines and totals (`benchmarks/reference.py`, with the calculation in its header comment).
  - Scenario `d3_ref_05` was renamed to say honestly that it does not exercise multiple packs.
- **D4 unsupported figure.** Deleted `results/figures/10_nlu_training_and_comparison_curves.png` and its notebook 04 display cell. No committed code trained DistilBERT or produced it. It is regenerated from real logs in Phase 6.
- **D5 answer leak** (`retrieval/evaluation.py`): the evaluator no longer passes the gold `required_ingredient` to the eligibility filter. Rankings are scored over the whole catalog; only request-side constraints (unit, diet) are applied.
- **D5 TF-IDF** (`retrieval/tfidf.py`): ranks the whole catalog deterministically (score, then product ID) and keeps zero-score items, so both retrievers return equal-length lists.
- `results/figures/README.md`: figure 10 is marked as removed and figure 11 as superseded.

**Verification evidence**

- `pytest`: **63 passed, 95 subtests** (55 before, plus 8 new regression tests).
  - Pantry stock reduces purchased flour (1 pack → 0).
  - A wrong expected line fails a scenario.
  - A wrong expected total fails a scenario.
  - An unmatched pantry key is reported and fails a scenario.
  - A missing product option gives an `incomplete` basket.
  - The retrieval evaluator never receives the gold ingredient.
  - A wrong-ingredient product ranked first is penalised (MRR 0.5).
  - TF-IDF returns a deterministic full-length ranking.
- `results/predictions/baseline_outputs.json` re-exported: 5/5 scenarios pass the stricter checks. The pantry scenario total is now 41000 minor units (was 50000).
- `results/predictions/retrieval_benchmark_results.json` re-run with the fixed evaluator. Test split, before → after the fix:

  | Retriever | Recall@10 | MRR |
  | --- | --- | --- |
  | MiniLM | 0.957 → 0.957 | 0.960 → 0.848 |
  | TF-IDF | 0.450 → 0.690 | 0.450 → 0.491 |

**Open limitations (carried to later phases)**

- The retrieval numbers above are **provisional**. Dev and test queries share the same 11 pilot ingredients, and the catalog has only 20 products. The grouped split and full catalog come in Phases 4 and 7. Do not cite these numbers or figure 11 in the report.
- Figure 09 (intent confusion matrix) also has no committed plotting code; it is regenerated in Phase 6.
- The NLU metrics in `results/predictions/nlu_evaluation_results.json` are still from 8 training examples, and the DistilBERT models remain untrained (Phase 6).
- The baseline still uses keyword intent rules and matches products by ingredient ID without a retrieval step (Phase 5).

## Earlier history (before the phase plan)

### Completed

- Read the proposal, build plan, and literature matrix; established the project scope.
- Initialized the local checkout and project structure.
- Compared candidate datasets and documented source limitations.
- Located the user-supplied Instacart and Food.com ZIP files.
- Implemented and ran a reproducible source audit with six passing correctness tests.
- Recorded archive SHA-256 hashes, file inventory, source columns, and quality checks.
- Scanned all six Instacart CSVs and the complete Food.com recipe CSV.
- Created a private 50-recipe review shortlist; all candidates remain unverified.
- Defined executable ingredient, conversion, product, recipe, and provenance contracts.
- Added three separately source-checked recipe examples, eleven canonical ingredients,
  and twenty simulated product options covering all twelve recipe lines.
- Preserved gram/millilitre/piece distinctions, documented flour conversion assumptions,
  and marked all three independent recipe reviews as pending.
- Ran all 18 unit tests successfully, including 12 pilot-contract tests, and checked
  the scaled-requirements CLI on the seed.
- The student implemented `packs_needed()` and `missing_amount()`; both passed
  their boundary and decimal-arithmetic checks on 21 October 2026.
- Added seven regression tests covering those helpers and their composition.
  The combined suite now contains 25 passing tests.
- The student implemented `line_cost_minor()`; review added explicit integer-type
  validation before comparisons, including rejection of booleans. Six cost tests
  cover boundaries, types, precision, and pantry-to-pack-to-cost composition.
  The combined suite now contains 31 passing tests.
- The student implemented `evaluate_product_option()` and corrected catalog-key
  lookups and local-variable handling through review. Seven option tests verify
  quantities, packs, price, surplus, incompatible inputs, unchanged catalog records,
  and two actual seed products. The combined suite now has 38 passing tests.

- Later work by member 1 (before 2026-11-25): baseline pipeline and benchmark (D3),
  NLU skeleton (D4) and retrieval (D5). See BUILD_PHASES.md section 2 for its status.
- 2026-11-25: Python 3.11 `.venv`, completed `requirements.txt` and a verified
  `requirements-lock.txt`. Raw archives restored to `data/raw/`; their SHA-256 hashes
  match the audit below exactly.

### Initial audit findings

The supplied Instacart files contain 206,209 users, 3,421,083 orders, 49,688
products, 32,434,489 prior purchase rows, and 1,384,617 training purchase rows.
Primary-key, product/category reference, order reference, cart-position, and
duplicate basket-item checks passed within the documented audit scope.

Food.com contains 522,517 recipes. Of those, 407,537 (77.99%) have mismatched
ingredient and quantity list lengths, and 182,911 have missing or invalid servings.
Only 48,339 pass the current structural checks before unit review. These are
overlapping checks, and none of these counts establishes optimizer readiness.
The recipe CSV has no dedicated ingredient-unit column.

Evidence: [audit report](data_audit.md), [source dictionary](data_dictionary.md),
and the ignored `data/interim/audit/summary.json` and `recipe_candidates.csv` files.

### Pilot data work (superseded by Phase 2)

The first examples and [their contracts](pilot_data.md) are implemented. They are
development data, not locked benchmark examples. Simulated product prices and
attributes are declared explicitly. No Instacart/Open Food Facts SKU joins or
product dietary claims have been established.

The original five-recipe target currently has three source-checked examples.
One is pasta dough rather than a complete dinner. Add two more usable meal
recipes, complete independent review, and write five expected basket examples.
The original acquisition plan below remains the acceptance checklist:

1. Define the recipe, ingredient, product, mapping, and review/provenance columns.
2. Review five suitable meal recipes from the shortlist against recorded sources.
   Verify servings, quantity-to-ingredient attachment, units, alternatives, and
   pantry assumptions. Reject unresolved records; do not guess missing units.
3. Create canonical ingredient IDs and reviewed synonyms.
4. Assemble 20 product options that cover the accepted recipes, with explicit pack
   sizes, compatible units, dietary evidence or unknown status, and fixed simulated
   prices in one currency.
5. Check recipe-to-product mapping coverage and define five structured requests
   with manually calculated expected quantities, pack counts, and totals.

Completion evidence: five accepted recipes, a covering 20-option catalog,
reviewed mappings, and five expected basket examples. No recipe is marked
ready while its required quantities or units remain unresolved.

## Next task (awaiting permission)

**Phase 12 — D10 report, package and demo** (BUILD_PHASES Phase 12). Nothing in it may
change a result; every number in the report comes from the Phase 11 files.

- Finish the literature review (15 papers; the closest work read in full), using the
  team's literature matrix in `docs/literature/`.
- Write the report in `docs/report/` (abstract last): introduction, literature review,
  methodology, implementation, results and discussion (from `results/tables/`, figures
  14–18 and `docs/failure_analysis.md`), conclusion answering RQ1–RQ3.
  - Report the baseline-parser win (A1 − E4), the null retrieval and association effects
    on baskets and the missed targets as they are.
  - State the skipped pre-run commit and the checksum evidence.
- README: setup, the reproducible commands (`prepare_data`, `train_nlu`, `build_index`,
  `mine_rules`, `evaluate_all`, `streamlit run app.py`), data and model acquisition, and
  sample inputs.
- A clean-environment run (fresh `.venv`, `pytest`, `evaluate_all.py --check`) and
  `results/run_manifest.json` (seeds, package versions, model revisions, input hashes).
- Rehearse the six demo cases; prepare the viva points (one request end to end, the
  baseline, one failure, one ablation).

Outstanding: the second-person annotation review (Phase 4), and independent reviews of
the recipes and the Instacart mapping.
Completion criteria are in [BUILD_PHASES.md](BUILD_PHASES.md).

After each phase, record what changed, the verification evidence, the open
limitations and the next task here.
