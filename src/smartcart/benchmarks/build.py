"""Assemble NLU seeds and basket scenarios from recipe and grocery-list families (Phase 4)."""

from __future__ import annotations

import hashlib
import random
from decimal import Decimal

from smartcart.benchmarks.language import choice, shuffled, to_catalog_amount
from smartcart.benchmarks.requests import (
    LIST_CATEGORIES, LIST_EXCLUDED, UNKNOWN_MEALS, Vocabulary, build_gold, excludable, list_quantity, min_cost,
    nice_quantity, round_up,
)
from smartcart.data.contracts import requirements_for
from smartcart.validation.feasibility import DIETS, check_feasibility

PLAN_DESIGNS = {
    "feasible": ["generous", "no_budget", "exact", "pantry_partial", "pantry_full", "exclusion", "exclusion_outside",
                 "diet_ok", "multipack"],
    "infeasible": ["budget_low", "one_short", "diet_conflict"],
    "clarification": ["vague_budget", "pantry_unknown", "ambiguous_diet", "broad", "unknown_meal"],
}
LIST_DESIGNS = {
    "feasible": ["list_generous", "list_no_budget", "list_exact"],
    "infeasible": ["list_budget_low", "list_diet_conflict"],
    "clarification": ["list_missing_quantity", "list_vague_budget"],
}
OUTSIDE_EXCLUSIONS = ["peanuts", "peanut_butter", "mushroom", "coconut_milk", "mozzarella", "firm_tofu"]


def stable_rng(*parts) -> random.Random:
    digest = hashlib.sha256(":".join(map(str, parts)).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


class FamilyBank:
    """Recipes and grocery-list families available to one split."""

    def __init__(self, vocab: Vocabulary, split: str, recipe_ids: list[str], n_lists: int, seed: int):
        self.vocab, self.split = vocab, split
        self.recipe_ids = sorted(recipe_ids)
        pool = sorted({line["ingredient_id"] for rid in self.recipe_ids for line in vocab.recipes[rid]["ingredients"]
                       if vocab.category[line["ingredient_id"]] in LIST_CATEGORIES
                       and line["ingredient_id"] not in LIST_EXCLUDED})
        self.lists = {}
        for k in range(n_lists):
            rng = stable_rng(seed, split, "list", k)
            size = 2 + int(rng.random() * 4)
            self.lists[f"list_{split}_{k:02d}"] = sorted(shuffled(rng, pool)[:size])

    def families(self) -> list[str]:
        return self.recipe_ids + sorted(self.lists)


def _budget_from(cost_minor: int, rng, low: float, high: float, step: int = 50) -> int:
    rupees = cost_minor / 100
    return round_up(int(rupees * (low + rng.random() * (high - low))) + 1, step)


def _diet_split(vocab: Vocabulary, request: dict) -> tuple[list[str], list[str]]:
    ok, bad = [], []
    for diet in DIETS:
        result = check_feasibility({**request, "diet": [diet], "budget_minor": None}, vocab.catalog)
        (ok if result["label"] == "feasible" else bad).append(diet)
    return ok, bad


def _single_unit_lines(vocab: Vocabulary, rid: str, servings: int) -> list[dict]:
    lines = requirements_for(vocab.catalog, rid, servings)
    counts = {}
    for line in lines:
        counts[line["ingredient_id"]] = counts.get(line["ingredient_id"], 0) + 1
    return [line for line in lines if counts[line["ingredient_id"]] == 1]


def suggestions(vocab: Vocabulary, spec: dict, limit: int = 3) -> list[str]:
    """Up to three supported recipes that are feasible under the spec's diet, budget and servings."""
    ranked = []
    for rid in sorted(vocab.recipes):
        probe = {"intent": "plan_meal", "recipe_id": rid, "servings": spec.get("servings"), "items": [],
                 "pantry": {}, "budget_minor": None if spec.get("budget") is None else spec["budget"] * 100,
                 "diet": spec.get("diet", []), "exclusions": []}
        result = check_feasibility(probe, vocab.catalog)
        if result["label"] == "feasible":
            ranked.append((result["min_cost_minor"], rid))
    return [rid for _, rid in sorted(ranked)[:limit]]


def plan_spec(vocab: Vocabulary, rid: str, design: str, rng, split: str) -> dict | None:
    """A plan_meal spec for one design, or None if the design does not apply to this recipe."""
    recipe = vocab.recipes[rid]
    servings = choice(rng, [2, 3, 4, 4, 5, 6, 8]) if rng.random() < 0.85 else None
    if design == "multipack":
        servings = min(12, recipe["base_servings"] * choice(rng, [2, 3]))
    spec = {"intent": "plan_meal", "split": split, "family_id": rid, "recipe_id": rid, "meal_kind": "recipe",
            "servings": servings, "budget": None, "diet": [], "exclusions": [], "pantry": [], "items": [],
            "clarification_type": None, "design": design}
    effective = servings or recipe["base_servings"]
    request = {"intent": "plan_meal", "recipe_id": rid, "servings": servings, "items": [], "pantry": {},
               "diet": [], "exclusions": []}
    base_cost = min_cost(vocab.catalog, request)
    if base_cost is None:
        return None
    lines = _single_unit_lines(vocab, rid, effective)

    if design in {"generous", "multipack"}:
        spec["budget"] = _budget_from(base_cost, rng, 1.1, 1.6)
    elif design == "no_budget":
        pass
    elif design == "exact":
        spec["budget"] = base_cost // 100
    elif design in {"pantry_partial", "pantry_full", "pantry_unknown"}:
        rng_lines = shuffled(rng, lines)
        for line in rng_lines:
            if design == "pantry_unknown":
                spec["pantry"] = [{"ingredient_id": line["ingredient_id"], "quantity": None,
                                   "user_unit": {"g": "g", "ml": "ml", "piece": "piece"}[line["unit"]]}]
                spec["clarification_type"] = "missing_pantry_quantity"
                spec["budget"] = _budget_from(base_cost, rng, 1.1, 1.5)
                break
            picked = nice_quantity(rng, line["unit"], Decimal(line["amount"]), "full" if design == "pantry_full" else "partial")
            if picked:
                spec["pantry"] = [{"ingredient_id": line["ingredient_id"], "quantity": str(picked[0]), "user_unit": picked[1]}]
                break
        if not spec["pantry"]:
            return None
        if design != "pantry_unknown":
            cost = min_cost(vocab.catalog, {**request, "pantry": {spec["pantry"][0]["ingredient_id"]:
                                                                  to_catalog_amount(Decimal(spec["pantry"][0]["quantity"]),
                                                                                    spec["pantry"][0]["user_unit"])[1]}})
            if design == "pantry_full":
                if cost == base_cost:
                    return None  # pantry must change the cheapest basket for this design
                spec["budget"] = cost // 100
            else:
                spec["budget"] = _budget_from(cost, rng, 1.1, 1.5)
    elif design == "exclusion":
        candidates = excludable(vocab, rid)
        if not candidates:
            return None
        spec["exclusions"] = [choice(rng, candidates)]
        cost = min_cost(vocab.catalog, {**request, "exclusions": spec["exclusions"]})
        spec["budget"] = _budget_from(cost, rng, 1.05, 1.4)
    elif design == "exclusion_outside":
        used = {line["ingredient_id"] for line in recipe["ingredients"]}
        outside = [i for i in OUTSIDE_EXCLUSIONS if i not in used]
        spec["exclusions"] = [choice(rng, outside)]
        spec["budget"] = _budget_from(base_cost, rng, 1.1, 1.5)
    elif design in {"diet_ok", "diet_conflict"}:
        ok, bad = _diet_split(vocab, request)
        options = ok if design == "diet_ok" else bad
        if not options:
            return None
        spec["diet"] = [choice(rng, options)]
        cost = min_cost(vocab.catalog, {**request, "diet": spec["diet"]}) if design == "diet_ok" else base_cost
        spec["budget"] = _budget_from(cost, rng, 1.1, 1.5)
    elif design == "budget_low":
        spec["budget"] = max(50, (int(base_cost / 100 * (0.5 + rng.random() * 0.35)) // 50) * 50)
        if spec["budget"] * 100 >= base_cost:
            return None
    elif design == "one_short":
        spec["budget"] = base_cost // 100 - 1
    elif design == "vague_budget":
        spec["budget_vague"] = True
        spec["clarification_type"] = "missing_budget"
    elif design == "ambiguous_diet":
        spec["diet_ambiguous"] = True
        spec["clarification_type"] = "ambiguous_diet"
        spec["budget"] = _budget_from(base_cost, rng, 1.1, 1.5)
    elif design in {"broad", "unknown_meal"}:
        spec.update(recipe_id=None, meal_kind="broad" if design == "broad" else "unknown",
                    clarification_type="missing_recipe")
        if design == "unknown_meal":
            spec["unknown_meal"] = choice(rng, UNKNOWN_MEALS[split])
        elif rng.random() < 0.5:
            spec["diet"] = [choice(rng, ["vegetarian", "vegetarian", "gluten_free", "dairy_free"])]
        spec["servings"] = spec["servings"] or 4
        spec["budget"] = choice(rng, [1500, 2000, 2500, 3000, None])
        spec["suggestions"] = suggestions(vocab, spec)
    else:
        raise ValueError(design)
    return spec


def list_spec(vocab: Vocabulary, family_id: str, ingredients: list[str], design: str, rng, split: str) -> dict | None:
    items = [dict(zip(("quantity", "user_unit"), (str(q), u)), ingredient_id=iid)
             for iid in ingredients for q, u in [list_quantity(rng, iid, vocab)]]
    spec = {"intent": "build_grocery_list", "split": split, "family_id": family_id, "recipe_id": None,
            "meal_kind": None, "servings": None, "budget": None, "diet": [], "exclusions": [], "pantry": [],
            "items": items, "clarification_type": None, "design": design}
    request = {"intent": "build_grocery_list", "items": [{"ingredient_id": e["ingredient_id"],
                                                          "amount": to_catalog_amount(Decimal(e["quantity"]), e["user_unit"])[1],
                                                          "unit": vocab.ingredients[e["ingredient_id"]]["supported_units"][0]}
                                                         for e in items], "pantry": {}, "diet": [], "exclusions": []}
    for entry, req in zip(items, request["items"]):
        if to_catalog_amount(Decimal(entry["quantity"]), entry["user_unit"])[0] != req["unit"]:
            return None
    base_cost = min_cost(vocab.catalog, request)
    if base_cost is None:
        return None
    if design == "list_generous":
        spec["budget"] = _budget_from(base_cost, rng, 1.1, 1.6)
    elif design == "list_no_budget":
        pass
    elif design == "list_exact":
        spec["budget"] = base_cost // 100
    elif design == "list_budget_low":
        spec["budget"] = max(50, (int(base_cost / 100 * (0.5 + rng.random() * 0.35)) // 50) * 50)
        if spec["budget"] * 100 >= base_cost:
            return None
    elif design == "list_diet_conflict":
        ok, bad = _diet_split(vocab, request)
        if not bad:
            return None
        spec["diet"] = [choice(rng, bad)]
        spec["budget"] = _budget_from(base_cost, rng, 1.1, 1.5)
    elif design == "list_missing_quantity":
        spec["items"][int(rng.random() * len(items))]["quantity"] = None
        spec["clarification_type"] = "missing_item_quantity"
        spec["budget"] = _budget_from(base_cost, rng, 1.2, 1.6)
    elif design == "list_vague_budget":
        spec["budget_vague"] = True
        spec["clarification_type"] = "missing_budget"
    else:
        raise ValueError(design)
    return spec


def gold_for(spec: dict, vocab: Vocabulary) -> dict:
    return build_gold(spec, vocab)


# ---------------------------------------------------------------- clarification answers
def resolve_clarification(spec: dict, vocab: Vocabulary, rng) -> tuple[str, dict]:
    """A user answer to the clarification and the resolved spec."""
    resolved = {**spec, "clarification_type": None, "pantry": [dict(p) for p in spec["pantry"]],
                "items": [dict(i) for i in spec["items"]], "budget_vague": False, "diet_ambiguous": False}
    kind = spec["clarification_type"]
    if kind == "missing_budget":
        request = gold_for({**resolved, "request_id": "probe", "budget": None}, vocab)
        rupees = _budget_from(min_cost(vocab.catalog, request), rng, 1.15, 1.6)
        resolved["budget"] = rupees
        return choice(rng, [f"about Rs {rupees}", f"{rupees} rupees", f"keep it under {rupees}"]), resolved
    if kind == "ambiguous_diet":
        request = gold_for({**resolved, "request_id": "probe"}, vocab)
        ok, _ = _diet_split(vocab, request)
        if ok and rng.random() < 0.7:
            diet = choice(rng, ok)
            resolved["diet"] = [diet]
            return {"vegetarian": "vegetarian please", "vegan": "vegan", "gluten_free": "gluten-free",
                    "dairy_free": "dairy-free", "nut_free": "nut-free"}[diet], resolved
        return "no restrictions, just normal", resolved
    if kind == "missing_pantry_quantity":
        entry = resolved["pantry"][0]
        servings = spec["servings"] or vocab.recipes[spec["recipe_id"]]["base_servings"]
        line = next(line for line in requirements_for(vocab.catalog, spec["recipe_id"], servings)
                    if line["ingredient_id"] == entry["ingredient_id"])
        picked = nice_quantity(rng, line["unit"], Decimal(line["amount"]), "partial") or \
            nice_quantity(rng, line["unit"], Decimal(line["amount"]), "full")
        entry["quantity"], entry["user_unit"] = str(picked[0]), picked[1]
        unit_word = {"piece": ""}.get(picked[1], picked[1])
        return f"{picked[0]} {unit_word}".strip(), resolved
    if kind == "missing_item_quantity":
        entry = next(i for i in resolved["items"] if i["quantity"] is None)
        q, u = list_quantity(rng, entry["ingredient_id"], vocab)
        entry["quantity"], entry["user_unit"] = str(q), u
        return f"{q} {'' if u == 'piece' else u}".strip(), resolved
    if kind == "missing_recipe":
        options = spec.get("suggestions") or []
        if not options:
            raise ValueError("no suggestion to answer with")
        rid = options[0]
        resolved.update(recipe_id=rid, meal_kind="recipe")
        return f"the {vocab.recipe_aliases[rid][0]}", resolved
    raise ValueError(kind)
