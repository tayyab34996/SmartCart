# Retrieval on the test split (100 queries)

| Setting | Recall@5 | Recall@10 | MRR | R@10 brand | R@10 constrained | R@10 misspelling | R@10 near_match | R@10 synonym | R@10 transliteration |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfidf_legacy_top10 (tfidf, legacy) | 0.552 | 0.610 | 0.562 | 0.615 | 0.857 | 0.432 | 0.882 | 0.772 | 0.056 |
| tfidf (tfidf, display_name_ingredient) | 0.549 | 0.610 | 0.555 | 0.615 | 0.857 | 0.432 | 0.882 | 0.772 | 0.056 |
| minilm (minilm, display_name_ingredient) | 0.696 | 0.764 | 0.713 | 0.827 | 1.000 | 0.909 | 0.941 | 0.902 | 0.111 |

Command: `python scripts/evaluate_components.py`.
