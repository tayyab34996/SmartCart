# Literature review — working comparison (D1)

Status: **skeleton (Phase 0)**. Finished in Phase 12.

## Inputs needed

- The team's existing **literature-matrix spreadsheet**. Add it to this folder
  (`docs/literature/`). It is a starting point, not a completed full-paper review.
- The lecture's list of allowed venues and its definition of "recent". The earlier
  selection spans 2019–2025.

## Rules for completing this review

- Read the methods and results of each paper. Do not rely on abstracts alone.
- Record the venue and track exactly, and distinguish main conference, Findings and
  demonstration tracks.
- Where database access was unavailable, check entries manually in Google Scholar.
- Fill a cell only from the paper itself. Leave it blank rather than guessing.
- Keep foundational (pre-"recent") work only if the instructor permits it.
- Do not describe SmartCart's combined approach as globally unique without a wider
  novelty search.

## Comparison table (15 papers)

Columns:

- **Task:** the problem the paper addresses.
- **Constraints handled:** budget, diet, quantity, completeness.
- **Method:** the technique used.
- **Data:** datasets used.
- **Evaluation:** metrics and baselines.
- **Relation to SmartCart:** closest overlap, the key difference, and what we reuse or contrast.

The first six rows are the papers the build plan names as closest work [S7]–[S12].
Their analysis cells are intentionally empty until each paper has been read.

| # | Paper | Venue / track | Task | Constraints handled | Method | Data | Evaluation | Relation to SmartCart |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Chen et al. 2021 — Personalized Food Recommendation as Constrained Question Answering over a Large-scale Food Knowledge Graph [S7] | | | | | | | |
| 2 | Li et al. 2023 — A Next Basket Recommendation Reality Check [S8] | | | | | | | |
| 3 | Hu et al. 2020 — Modeling Personalized Item Frequency Information for Next-basket Recommendation [S9] | | | | | | | |
| 4 | Reimers and Gurevych 2019 — Sentence-BERT [S10] | | | | | | | |
| 5 | Li et al. 2025 — ChatCRS [S11] | | | | | | | |
| 6 | Ariannezhad et al. 2022 — ReCANet [S12] | | | | | | | |
| 7 | *(from literature matrix)* | | | | | | | |
| 8 | *(from literature matrix)* | | | | | | | |
| 9 | *(from literature matrix)* | | | | | | | |
| 10 | *(from literature matrix)* | | | | | | | |
| 11 | *(from literature matrix)* | | | | | | | |
| 12 | *(from literature matrix)* | | | | | | | |
| 13 | *(from literature matrix)* | | | | | | | |
| 14 | *(from literature matrix)* | | | | | | | |
| 15 | *(from literature matrix)* | | | | | | | |

## Synthesis (to write in Phase 12)

1. Grocery and food recommendation under constraints.
2. Next-basket recommendation and repeat-purchase baselines.
3. Semantic retrieval and sentence embeddings.
4. Conversational recommendation and clarification.
5. **Gap:** no reviewed work evaluates complete, quantity-aware, budget-constrained
   baskets built from free-text requests against independent ranking. This claim must
   be confirmed against the full table before it is written into the report.

## Implementation sources (cite, but these are not part of the 15)

- [S1] Instacart Market Basket Analysis — dataset access
- [S2] Food.com Recipes and Reviews — irkaal dataset card
- [S3] scikit-learn — common pitfalls and data leakage
- [S4] Hugging Face Transformers — token classification guide
- [S5] Sentence Transformers — all-MiniLM-L6-v2 model card
- [S6] Google OR-Tools — CP-SAT solver and status handling
