"""Deterministic split groups: meal families for NLU and baskets, ingredients for retrieval."""

from __future__ import annotations

import hashlib

SPLITS = ("train", "dev", "test")


def _key(seed: int, name: str) -> str:
    return hashlib.sha256(f"{seed}:{name}".encode("utf-8")).hexdigest()


def split_meal_families(recipes: list[dict], seed: int, recipe_targets: dict[str, int]) -> dict[str, str]:
    """Assign whole meal families to splits so related recipes never cross splits.

    Families are visited in hash order, largest first within ties of size, and each goes
    to the split that is furthest below its recipe target.
    """
    sizes: dict[str, int] = {}
    for recipe in recipes:
        sizes[recipe["meal_family"]] = sizes.get(recipe["meal_family"], 0) + 1
    if sum(recipe_targets.values()) != sum(sizes.values()):
        raise ValueError("recipe targets must add up to the number of recipes")
    filled = {s: 0 for s in SPLITS}
    assignment = {}
    for family in sorted(sizes, key=lambda f: (-sizes[f], _key(seed, f))):
        split = max(SPLITS, key=lambda s: (recipe_targets[s] - filled[s], -SPLITS.index(s)))
        assignment[family] = split
        filled[split] += sizes[family]
    return dict(sorted(assignment.items()))


def split_ingredients(ingredient_ids: list[str], seed: int, dev_count: int) -> dict[str, str]:
    """Retrieval groups: the ``dev_count`` lowest-hash ingredients are dev, the rest test."""
    ordered = sorted(ingredient_ids, key=lambda i: _key(seed, i))
    return {i: ("dev" if n < dev_count else "test") for n, i in enumerate(ordered)}
