# SmartCart initial data audit

Generated: 2026-10-20T17:18:50.047805+00:00

This report describes source data, not model performance. Raw archives were read in place and not modified.

## Acquired archives

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `data/raw/archive_3.zip` | 207,073,669 | `c347cd7fa301c068ed391c7c77620f0e26e18f65d04cb907b6389c670db03038` |
| `data/raw/archive_4.zip` | 758,217,627 | `fa7910c9591997641448147809faa21b4bba539c01225fda2ab6b315b5f7527d` |

## Instacart

| Table | Rows |
| --- | ---: |
| aisles | 134 |
| departments | 21 |
| products | 49,688 |
| orders | 3,421,083 |
| Prior order products | 32,434,489 |
| Train order products | 1,384,617 |

Distinct users: **206,209**. Order evaluation sets: `{"prior": 3214874, "train": 131209, "test": 75000}`.

### Integrity checks

| Check | Count |
| --- | ---: |
| aisles: duplicate primary IDs | 0 |
| departments: duplicate primary IDs | 0 |
| products: duplicate primary IDs | 0 |
| orders: duplicate primary IDs | 0 |
| products: unknown_aisle_ids | 0 |
| products: unknown_department_ids | 0 |
| products: blank_names | 0 |
| prior: unknown_product_ids | 0 |
| prior: unknown_order_ids | 0 |
| prior: wrong_eval_set | 0 |
| prior: fragmented_order_groups | 0 |
| prior: duplicate_products_within_contiguous_order_group | 0 |
| prior: groups_with_noncontiguous_cart_positions | 0 |
| prior: orders_missing_product_rows | 0 |
| train: unknown_product_ids | 0 |
| train: unknown_order_ids | 0 |
| train: wrong_eval_set | 0 |
| train: fragmented_order_groups | 0 |
| train: duplicate_products_within_contiguous_order_group | 0 |
| train: groups_with_noncontiguous_cart_positions | 0 |
| train: orders_missing_product_rows | 0 |

The JSON summary contains additional numeric, flag, and missing-value checks. A global order/product duplicate conclusion requires zero fragmented order groups.

Missing `days_since_prior_order` on first orders is expected; cart position and reorder flags are not quantities.

## Food.com recipes

| Check | Count |
| --- | ---: |
| rows | 522,517 |
| duplicate_ids | 0 |
| missing_or_invalid_servings | 182,911 |
| unsupported_vector_syntax_rows | 0 |
| empty_ingredient_lists | 2,219 |
| ingredient_quantity_length_mismatches | 407,537 |
| rows_with_missing_ingredient_names | 0 |
| rows_with_missing_quantity_entries | 180,758 |
| rows_with_nonpositive_or_unparsed_amounts | 221,415 |
| structurally_usable_before_unit_review | 48,339 |
| meal_shortlist_candidates_before_unit_review | 7,484 |
| shortlist_count | 50 |

Dedicated ingredient-unit column detected: **False**.
A structurally usable row is not a verified quantity-aware recipe. Positive numeric amounts and matching list lengths do not establish units, recipe correctness, dietary suitability, or product mappings.

Recipe issue counts can overlap. Ingredient/amount checks exclude rows with unsupported vector syntax; servings and identifier checks cover all rows.

## Coverage and limitations

- All six Instacart CSVs and the complete Food.com recipe CSV were scanned. ZIP CRC is checked by the reader for fully consumed members.
- The archive SHA-256 hashes identify the downloaded files; they were not compared to publisher-provided checksums. Dataset release/version and actual download date are not independently established.
- Review data and Parquet files were inventoried but not scanned. No full-archive integrity claim is made.
- Recipe list parsing is deliberately limited and does not execute source strings. Unsupported rows are counted for review.
- No missing units, prices, pack sizes, or dietary attributes were fabricated. No model has been trained.
- Purchase history remains separate from recipe fulfillment; no product identity joins have been accepted.

## Reproduce

```powershell
python scripts/audit_data.py --config configs/data_audit.json
```

Machine-readable manifest and checks are saved under `data/interim/audit/`. Recipe candidate records remain there rather than in public documentation.

## Next task

Review five meal recipes and establish their actual quantities, units, and servings from recorded sources. Then build their canonical ingredient mappings and a covering 20-option product catalog with explicit pack sizes and simulated prices. Recipes with unresolved units remain excluded from optimization.
