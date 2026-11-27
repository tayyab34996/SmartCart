"""FP-Growth association rules on training transactions, and the bounded pair score (Phase 8).

Itemsets are mined once at the lowest count in the grid (``min_count_floor``); every
threshold in the grid is then a filter on the same rules, so the grid search does not
re-mine. Counts are exact integers (support x number of transactions, rounded).

``pair_score(a, b) = 1 - 1/lift`` for a pair that passes the thresholds and has
lift > 1, else 0. Lift is symmetric, so the score is too. It lies in [0, 1]: it is
rounded to 6 decimals, so only a lift above 10^6 would round to 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DECIMALS = 6


def one_hot(transactions: list[frozenset[str]], items: list[str]) -> pd.DataFrame:
    """Boolean transaction matrix, one column per item in ``items`` order."""
    col = {item: j for j, item in enumerate(items)}
    matrix = np.zeros((len(transactions), len(items)), dtype=bool)
    for i, basket in enumerate(transactions):
        for item in basket:
            matrix[i, col[item]] = True
    return pd.DataFrame(matrix, columns=items)


def mine_itemsets(frame: pd.DataFrame, min_count: int, max_len: int) -> pd.DataFrame:
    from mlxtend.frequent_patterns import fpgrowth

    n = len(frame)
    present = frame.loc[:, frame.any(axis=0)]  # fpgrowth needs at least one True per column
    itemsets = fpgrowth(present, min_support=min_count / n, use_colnames=True, max_len=max_len)
    itemsets["count"] = (itemsets["support"] * n).round().astype(int)
    return itemsets[itemsets["count"] >= min_count].reset_index(drop=True)


def mine_rules(itemsets: pd.DataFrame, n_transactions: int) -> list[dict]:
    """Every rule from the itemsets (confidence >= 0), sorted deterministically."""
    from mlxtend.frequent_patterns import association_rules

    if not (itemsets["itemsets"].map(len) > 1).any():
        return []
    rules = association_rules(itemsets, num_itemsets=n_transactions, metric="confidence", min_threshold=0.0)
    counts = {frozenset(s): c for s, c in zip(itemsets["itemsets"], itemsets["count"])}
    out = []
    for ante, cons, conf, lift in zip(rules["antecedents"], rules["consequents"], rules["confidence"], rules["lift"]):
        count = counts[frozenset(ante) | frozenset(cons)]
        out.append({"antecedent": "|".join(sorted(ante)), "consequent": "|".join(sorted(cons)),
                    "length": len(ante) + len(cons), "count": int(count),
                    "support": round(count / n_transactions, DECIMALS),
                    "confidence": round(float(conf), DECIMALS), "lift": round(float(lift), DECIMALS)})
    out.sort(key=lambda r: (r["length"], r["antecedent"], r["consequent"]))
    return out


def pair_table(rules: list[dict]) -> dict[tuple[str, str], dict]:
    """Per unordered pair (a < b): count, lift and both directional confidences."""
    pairs: dict[tuple[str, str], dict] = {}
    for r in rules:
        if r["length"] != 2:
            continue
        a, b = r["antecedent"], r["consequent"]
        key = (a, b) if a < b else (b, a)
        entry = pairs.setdefault(key, {"count": r["count"], "lift": r["lift"]})
        entry["confidence_" + ("ab" if a < b else "ba")] = r["confidence"]
    return pairs


def passes(entry: dict, min_count: int, min_confidence: float) -> bool:
    best = max(entry.get("confidence_ab", 0.0), entry.get("confidence_ba", 0.0))
    return entry["count"] >= min_count and best >= min_confidence


def lift_to_score(lift: float) -> float:
    return round(1.0 - 1.0 / lift, DECIMALS) if lift > 1.0 else 0.0


def pair_matrix(pairs: dict, items: list[str], min_count: int, min_confidence: float) -> np.ndarray:
    """Symmetric item x item pair scores (zero diagonal) under the given thresholds."""
    col = {item: j for j, item in enumerate(items)}
    matrix = np.zeros((len(items), len(items)))
    for (a, b), entry in pairs.items():
        if passes(entry, min_count, min_confidence):
            matrix[col[a], col[b]] = matrix[col[b], col[a]] = lift_to_score(entry["lift"])
    return matrix


def filter_rules(rules: list[dict], min_count: int, min_confidence: float) -> list[dict]:
    """Rules kept for export: pairs by the pair test, longer rules by their own count and confidence."""
    pairs = pair_table(rules)
    kept = []
    for r in rules:
        if r["length"] == 2:
            a, b = r["antecedent"], r["consequent"]
            if passes(pairs[(a, b) if a < b else (b, a)], min_count, min_confidence):
                kept.append(r)
        elif r["count"] >= min_count and r["confidence"] >= min_confidence:
            kept.append(r)
    return kept
