# SmartCart — Scope, contribution and research questions (D1)

## Problem and user scenario

A shopper types a request in plain English, for example *"vegetarian pasta dinner for
four under 2,000 rupees, I already have 250 g of flour."* SmartCart is an **offline
virtual grocery assistant**. It turns the request into a complete, quantity-aware
basket that:

- covers every required ingredient in whole product packs;
- subtracts what the shopper already has;
- stays within the stated budget;
- respects dietary rules and exclusions.

When the request is ambiguous, SmartCart asks a short clarification question. When no
valid basket exists, it says so and does not return a basket that breaks the rules.

## Pipeline

1. Read the request. Extract intent and structured constraints: meal, products,
   servings, quantities and units, budget, diet, exclusions, pantry items.
2. Ask for missing or ambiguous information (budget, amount, diet, meal).
3. Resolve a supported recipe or an explicit grocery list. Scale to the requested
   servings, aggregate repeated ingredients and subtract pantry stock.
4. Retrieve candidate products for each remaining ingredient.
5. Add optional purchase-history and association scores.
6. Select the basket under hard constraints, then validate it independently.
7. Show product packs, total cost, missing information and short explanations.

## Core scope

| In scope | Out of scope (future work) |
| --- | --- |
| English text requests | Voice and image input |
| One offline catalog in one currency (PKR) | Live inventory, multi-store pricing |
| Curated recipes (Food.com, manually normalized) | Real checkout and payment |
| Optional purchase history (Instacart) | Mixing brands to cover one ingredient, multi-ingredient bundles |
| Streamlit demonstration | A web backend, vector-database services, paid LLM calls |

**Prices are simulated.** Product prices and pack attributes are a PKR-labelled
simulation. Every simulated attribute is flagged in the catalog, and every interface
screen shows it. Results support an offline comparison of methods, not claims about
real supermarket savings.

## Contribution

We evaluate whether semantic retrieval and basket-aware scoring, combined with explicit
quantity and budget constraints, produce more useful grocery baskets than independent
item ranking with post-hoc filtering.

This is a course-project contribution: a controlled comparison on complete constrained
baskets. It does not propose a new algorithm or claim a first-ever system. It will not
be described as globally unique without a wider novelty search.

## Research questions

- **RQ1:** Does semantic retrieval (MiniLM + FAISS) improve product matching over a
  lexical baseline (TF-IDF) on grocery paraphrases and ingredient synonyms?
- **RQ2:** Does explicit constrained selection (OR-Tools CP-SAT) improve the rate of
  valid complete baskets over independent ranking with post-hoc filtering?
- **RQ3:** Once the same hard constraints are enforced, does association-aware scoring
  add useful basket relevance or personalized ranking value?

RQ3 may show a small or negative gain, and that outcome will be reported as it is.
Coverage constraints already force complete baskets, so association scoring cannot
take credit for completeness.

## Definition of success

The primary outcome is **valid complete success**. A basket counts as a success only if
it meets all of these conditions, checked against the *annotated* request, including
constraints the parser missed:

- every required ingredient and quantity is covered;
- every hard rule (diet, exclusions) is met;
- only correct catalog items are used;
- the total is within budget.

Feasible, infeasible and clarification scenarios are scored separately. Refusing a
feasible request counts as a failure, and failed outputs stay in every denominator.

Proposed engineering targets (intent Macro-F1 ≥ 0.85, Recall@10 ≥ 0.90, ≥ 90% valid
complete success on feasible scenarios, zero violations among outputs labelled valid,
and others) are listed in [BUILD_PHASES.md](BUILD_PHASES.md) section 6. They are
targets, not results. Actual values will be reported, and missed targets explained.

## Evaluation tracks

- **Track A — grocery goals.** Uses the curated catalog and annotated requests. The
  main outcome is a valid complete basket.
- **Track B — historical next-basket ranking.** Uses held-out Instacart orders.

Track B purchase-prediction scores are never presented as evidence that meal requests
were fulfilled in Track A.

## Assessment criteria

| Criterion | Weight |
| --- | --- |
| Originality and Innovation | 20% |
| Technical Depth | 25% |
| Implementation and Results | 30% |
| Report Quality | 15% |

These criteria total 90%; the remaining 10% is unspecified. The earlier "Final Project
Report with Code Submission — 85%" appears to be a separate assessment weight. The full
rubric is to be confirmed with the instructor; the figures are not rescaled or combined
until then.
