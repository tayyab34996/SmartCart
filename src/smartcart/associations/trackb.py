"""Track B next-basket ranking at ingredient level (Phase 8).

Three rankers over the same item universe and list length:

- **popularity**: training-order count over all sampled users;
- **frequency**: the user's personalised item frequency [S9] (share of their history
  orders containing the item);
- **association**: frequency + ``weight`` x the frequency-weighted mean pair score
  between the item and the user's other history items.

Ties always go to popularity and then to the item ID, so every list has exactly
``list_length`` items and no ranker gets extra slots. Metrics are Recall@k and binary
NDCG@k, overall and restricted to repeat items (in the user's history) and new items.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

RANKERS = ("popularity", "frequency", "association")
SCORE_DECIMALS = 9


@dataclass
class Users:
    """History and targets for the users being evaluated, rows aligned."""

    ids: list[int]
    frequency: np.ndarray      # users x items, share of history orders containing the item
    targets: list[set[int]]    # item column indices in the target order


def history_matrix(trackb, users: list[int], history_splits: tuple[str, ...]) -> np.ndarray:
    col = {item: j for j, item in enumerate(trackb.items)}
    freq = np.zeros((len(users), len(trackb.items)))
    for r, user in enumerate(users):
        orders = [o for s in history_splits for o in trackb.user_orders[user].get(s, [])]
        for o in orders:
            for item in trackb.orders[o]:
                freq[r, col[item]] += 1
        freq[r] /= max(len(orders), 1)
    return freq


def popularity(trackb, splits: tuple[str, ...] = ("train",)) -> np.ndarray:
    col = {item: j for j, item in enumerate(trackb.items)}
    counts = np.zeros(len(trackb.items))
    for s in splits:
        for o in trackb.split_orders(s):
            for item in trackb.orders[o]:
                counts[col[item]] += 1
    return counts


def build_users(trackb, target_split: str, history_splits: tuple[str, ...]) -> tuple[Users, int]:
    """Users with a non-empty target order, and the number excluded for an empty one."""
    col = {item: j for j, item in enumerate(trackb.items)}
    ids, targets, excluded = [], [], 0
    for user in sorted(trackb.user_orders):
        (order,) = trackb.user_orders[user][target_split]
        target = {col[i] for i in trackb.orders[order]}
        if not target:
            excluded += 1
            continue
        ids.append(user)
        targets.append(target)
    return Users(ids, history_matrix(trackb, ids, history_splits), targets), excluded


def association_term(frequency: np.ndarray, pairs: np.ndarray) -> np.ndarray:
    """sum_{j != i} f(j) P(i, j) / sum_{j != i} f(j); 0 where the user has no other history."""
    num = frequency @ pairs  # pairs is symmetric with a zero diagonal
    den = frequency.sum(axis=1, keepdims=True) - frequency
    return np.divide(num, den, out=np.zeros_like(num), where=den > 0)


def scores(ranker: str, users: Users, pairs: np.ndarray | None = None, weight: float = 0.0) -> np.ndarray:
    if ranker == "popularity":
        return np.zeros_like(users.frequency)
    if ranker == "frequency":
        return users.frequency.copy()
    if ranker == "association":
        return users.frequency + weight * association_term(users.frequency, pairs)
    raise ValueError(f"unknown ranker {ranker}")


def top_k(score: np.ndarray, pop: np.ndarray, k: int) -> np.ndarray:
    """Top-k item indices per row: score, then popularity, then item index (items are sorted by ID)."""
    rounded = np.round(score, SCORE_DECIMALS)
    idx = np.arange(score.shape[1])
    out = np.empty((score.shape[0], k), dtype=int)
    for r in range(score.shape[0]):
        out[r] = np.lexsort((idx, -pop, -rounded[r]))[:k]
    return out


def _dcg(hits: list[bool]) -> float:
    return sum(1.0 / np.log2(i + 2) for i, h in enumerate(hits) if h)


def user_metrics(ranked: list[int], target: set[int], k: int) -> dict:
    hits = [i in target for i in ranked[:k]]
    ideal = _dcg([True] * min(len(target), k))
    return {"recall": sum(hits) / len(target), "ndcg": _dcg(hits) / ideal}


def evaluate(ranked: np.ndarray, users: Users, k: int) -> list[dict]:
    """Per-user metrics: all target items, repeat items and new items (None when empty)."""
    rows = []
    for r, target in enumerate(users.targets):
        history = set(np.flatnonzero(users.frequency[r] > 0))
        lst = ranked[r].tolist()
        row = {"user_id": users.ids[r], "all": user_metrics(lst, target, k)}
        for name, subset in (("repeat", target & history), ("new", target - history)):
            row[name] = user_metrics(lst, subset, k) if subset else None
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    out = {"num_users": len(rows)}
    for part in ("all", "repeat", "new"):
        vals = [r[part] for r in rows if r[part] is not None]
        out[part] = {"num_users": len(vals),
                     "recall_at_10": round(float(np.mean([v["recall"] for v in vals])), 6) if vals else None,
                     "ndcg_at_10": round(float(np.mean([v["ndcg"] for v in vals])), 6) if vals else None}
    return out


def user_half(user_id: int, seed: int) -> str:
    digest = hashlib.sha256(f"{seed}:trackb-validation:{user_id}".encode("ascii")).hexdigest()
    return "tune" if int(digest, 16) % 2 == 0 else "report"


def subset(users: Users, keep: list[bool]) -> Users:
    rows = [i for i, k in enumerate(keep) if k]
    return Users([users.ids[i] for i in rows], users.frequency[rows], [users.targets[i] for i in rows])


def paired_bootstrap(a: list[float], b: list[float], resamples: int, seed: int) -> dict:
    """Mean of a - b with a 95% percentile interval over resampled users."""
    diff = np.asarray(a) - np.asarray(b)
    rng = np.random.default_rng(seed)
    means = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(resamples)])
    return {"mean_difference": round(float(diff.mean()), 6),
            "ci95": [round(float(np.percentile(means, 2.5)), 6), round(float(np.percentile(means, 97.5)), 6)],
            "users": len(diff)}
