# Track B (test order; history train, validation; rules from training orders)

Users: 7413 evaluated, 2587 excluded (no mapped ingredient in the target order).

| Ranker | Recall@10 | NDCG@10 | Repeat R@10 | Repeat NDCG@10 | New R@10 | New NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- |
| popularity | 0.502 | 0.361 | 0.573 | 0.402 | 0.261 | 0.135 |
| frequency | 0.703 | 0.582 | 0.903 | 0.724 | 0.104 | 0.042 |
| association | 0.686 | 0.572 | 0.895 | 0.716 | 0.073 | 0.030 |

| Paired bootstrap (users) | Mean difference | 95% interval |
| --- | --- | --- |
| association_minus_frequency_ndcg_at_10 | -0.0105 | [-0.0122, -0.0089] |
| association_minus_frequency_recall_at_10 | -0.0170 | [-0.0204, -0.0135] |
| frequency_minus_popularity_ndcg_at_10 | +0.2213 | [+0.2146, +0.2285] |
| frequency_minus_popularity_recall_at_10 | +0.2015 | [+0.1928, +0.2102] |

Command: `python scripts/evaluate_components.py`.
