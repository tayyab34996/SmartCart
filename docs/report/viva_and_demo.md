# Demo script and viva notes

Every outcome below comes from `results/metrics/demo_cases.json` (the six demo
conversations, DistilBERT parser) or from the test-split rows in
`results/predictions/runs/`.

## Before the demo

```powershell
cd C:\SmartCart
$env:HF_HUB_OFFLINE = "1"
.\.venv\Scripts\python -m streamlit run app.py
```

Start it a few minutes early: the first load takes about half a minute (PyTorch,
DistilBERT and MiniLM). Point at the **simulated-price banner** once at the start.

## The six cases

| # | Type this | What happens | What to point out |
| --- | --- | --- | --- |
| D1 | Pick a history user in the sidebar, then: *I'd like to cook chicken curry in a hurry for 4 people with a budget of 2500 rupees* | Valid basket, PKR 2,407 of 2,500 | "What I understood" (recipe, servings, budget, history user); packs vs need vs leftover; "Why these products" |
| D2 | *Plan honey lime chicken for 3 people, budget 3000 rupees*, then *Actually, can we do it for 1,200 rupees instead* | Valid (PKR 2,192), then **proven infeasible**, suggested budget PKR 2,192 | The revision is parsed in words; "What changed" names the budget; the request is not relaxed silently |
| D3 | *Something vegetarian for dinner for 3, keep it under 2500 rupees* → confirm the first suggestion → exclude the dearest line | Dish suggestions; valid basket (PKR 727); butter removed, PKR 487 | Broad goal → feasible, cheapest-first suggestions; vegetarian enforced; exclusion edit and "What changed" |
| D4 | *Get me everything for potato soup for 4 people within 2000 rupees, I already have some onion*, then *I have 2 onions* | Asks "How much onion do you already have (in piece)?"; then valid, PKR 1,847 | Clarification instead of guessing; the pantry is subtracted |
| D5 | *mates coming round tonight lol, fancy doing baked salmon, there'll be 6 of us and I can't spend more than 10000* | Valid, PKR 8,570 of 10,000 | Chatty wording still parsed |
| D6 | *Plan baked salmon for 6 people under 500 rupees* | Proven infeasible; suggested budget PKR 8,570; "use the suggested budget" button | Proof over the whole catalog, not a timeout; press the button to get the basket |

Finish with the CSV/JSON export buttons. If the transformer checkpoints are missing, the
app falls back to the baseline parser and says so; the six cases give the same statuses
and totals.

## Viva points

### One request end to end (test scenario `test_b000`, E4, seed 42)

*"Put together a basket for garlic green beans, cap it at Rs 750, enough for 2 and I'm
avoiding water"*

1. **Parse.** DistilBERT tags the dish, servings, budget and exclusion; normalisation gives
   `intent = plan_meal`, recipe `foodcom_43390`, servings 2, budget 75,000 paisa
   (PKR 750), exclusions `["water"]`.
2. **Resolve.** Recipe lines are scaled to 2 servings; the excluded ingredient (water) is
   dropped from the requirements; nothing is in the pantry. Five lines remain: green
   beans, garlic, butter, salt, black pepper.
3. **Retrieve.** For each line, MiniLM ranks the whole catalog for the canonical
   ingredient name and keeps the top 40.
4. **Hard rules.** Only candidates of the right ingredient and unit, available, not
   excluded (and `allowed` for any diet) become options.
5. **Solve.** CP-SAT picks one option per line within the budget: green beans 250 g
   (PKR 125), garlic 10 pieces (PKR 40), butter 100 g (PKR 240), salt 250 ml (PKR 30),
   black pepper 50 ml (PKR 150); total **PKR 585**, optimality proven.
6. **Validate.** The independent validator recomputes needs, packs, costs, rules and
   budget: coverage 1.0, valid. It equals the gold checker's minimum (PKR 585).

### Why the baseline is the way it is

- E0 is what a reasonable first system would do: a fast, well-understood intent
  classifier (TF-IDF + LinearSVC, tuned on validation), dictionary and rule slots over the
  catalog's own vocabulary, lexical retrieval, and the cheapest product per line followed
  by a diet/budget filter.
- It isolates the research questions: each later run changes one component (parser,
  retrieval, selector, association terms), so every difference is attributable.
- It is strong where the domain is closed (a fixed catalog vocabulary), which is why the
  rule parser wins end to end (A1). Be ready to say the caveat: its cue words were written
  by an agent that had read the generator's templates, which may favour it.

### One failure (`docs/failure_analysis.md`, case 5)

*"Sort out the groceries for green beans with garlic. for a family of 4, 743 is my limit"*
(`test_b007`): DistilBERT attaches "4" to the budget (PKR 4.00) and leaves servings unset.
CP-SAT then correctly proves that no basket fits PKR 4, so the system reports a **false
rejection**. The selector and validator did their job; the error entered at parsing. The
phrase "is my limit" and "for a family of" never appear in the 600 training texts. All
three seeds fail it; the baseline parser gets it right.

### One ablation

- **A4 − E4 (selection):** replace CP-SAT with the independent selector, everything else
  equal: −0.090 [−0.117, −0.064] with gold input. All of the loss is in diet scenarios,
  where the cheapest product is `unknown` for the diet and the post-hoc filter leaves the
  line uncovered. CP-SAT applies the diet first.
- **A1 − E4 (parser):** replace DistilBERT with the baseline parser: +0.133
  [+0.062, +0.218] end to end and 0 with gold input — the whole difference is parsing.

### Questions to expect

- *Why does MiniLM not help the baskets?* The pipeline queries canonical ingredient names,
  and both retrievers' candidate pools already contain the right products (E2 = E1,
  A2 = E4). MiniLM helps free-text queries (Recall@10 0.764 vs 0.610).
- *Why do associations not help?* Rules are at ingredient level (no catalog product has an
  Instacart ID), so all products of an ingredient score the same; on next-basket ranking
  they lower NDCG@10 by 0.0105 against personal frequency.
- *Are the prices real?* No. They are simulated PKR and labelled everywhere.
- *How do you know the test set was not tuned on?* Locked by SHA-256 before any model saw
  it; one evaluation run with frozen configs; `evaluate_all.py --check` reproduces every
  table. The configs were not committed before the run, but their checksums were
  recorded before and after and are identical.
- *What would you do next?* Confirm extracted constraints with the user before buying;
  train the parser on more varied phrasings; evaluate on requests written by real users.
