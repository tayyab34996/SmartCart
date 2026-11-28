# NLU on the test split (150 examples)

| Parser | Intent macro-F1 (classifier only) | Intent macro-F1 | Slot micro-F1 | Request exact match |
| --- | --- | --- | --- | --- |
| E0 baseline | 0.788 | 0.842 | 0.947 | 0.773 |
| DistilBERT (mean ± std, 3 seeds) | 0.936 ± 0.034 | 0.947 ± 0.028 | 0.972 ± 0.003 | 0.862 ± 0.006 |

Command: `python scripts/evaluate_components.py` (config `configs/experiments/evaluation.json`).
