"""Generate request specs, render them as annotated text, and build gold StructuredRequests.

A *spec* fixes the meaning of a request (intent, recipe, servings, budget, diet,
exclusions, pantry, items, clarification need). Several paraphrases of one spec share a
``seed_id`` and the same gold request. Phrasing templates are partitioned by split, so
dev and test text uses templates never seen in training. Lexical items (ingredient
aliases, unit words, number words) are shared vocabulary.

Labels come from construction, not from a model: every slot span is written by the
renderer together with its value, and BIO tags are derived from the spans.
"""

from __future__ import annotations

import re
from decimal import Decimal

from smartcart.benchmarks.language import (
    AMBIGUOUS_DIET_FORMS, DIET_FORMS, DIET_NEGATION_FORMS, USER_UNITS, TextBuilder, budget_surface, choice,
    number_surface, shuffled, to_catalog_amount, unit_words,
)
from smartcart.validation.feasibility import check_feasibility

DIET_NAMES = {"vegetarian": "vegetarian", "vegan": "vegan", "gluten_free": "gluten-free",
              "dairy_free": "dairy-free", "nut_free": "nut-free"}

# ---------------------------------------------------------------- phrasing pools by split
POOLS = {
    "meal_opener": {
        "train": ["I want to make {meal}", "help me cook {meal}", "plan {meal}", "{meal} please",
                  "get me everything for {meal}", "what do I need to buy for {meal}", "I'm cooking {meal} tonight",
                  "shopping list for {meal}", "let's make {meal}", "I need ingredients for {meal}",
                  "make {meal}", "can you plan {meal}"],
        "dev": ["thinking of making {meal}", "get the ingredients for {meal}", "I feel like {meal}"],
        "test": ["I'd like to prepare {meal}", "put together a basket for {meal}", "we're having {meal}",
                 "sort out the groceries for {meal}"],
    },
    "broad_opener": {
        "train": ["plan a {diet_adj}dinner", "I need a {diet_adj}meal idea", "what {diet_adj}dish should I cook tonight",
                  "make me some {diet_adj}lunch", "plan a {diet_adj}meal"],
        "dev": ["something {diet_adj}for dinner please", "pick a {diet_adj}dinner for me"],
        "test": ["help me sort out a {diet_adj}dinner", "suggest a {diet_adj}meal", "what {diet_adj}food can I make"],
    },
    "servings": {
        "train": ["for {n}", "for {n} people", "serves {n}", "{n} servings", "for {n} persons"],
        "dev": ["feeding {n}", "{n} portions"],
        "test": ["for a family of {n}", "enough for {n}", "{n} of us are eating"],
    },
    "budget": {
        "train": ["under {budget}", "budget {budget}", "max {budget}", "keep it below {budget}", "within {budget}",
                  "my budget is {budget}", "budget of {budget}"],
        "dev": ["no more than {budget}", "spend up to {budget}"],
        "test": ["spending at most {budget}", "I can spend {budget}", "cap it at {budget}", "{budget} is my limit"],
    },
    "vague_budget": {
        "train": ["on a budget", "keep it cheap", "cheap please", "not expensive"],
        "dev": ["not too expensive", "budget friendly"],
        "test": ["as cheap as you can", "I'm short on money", "affordable please"],
    },
    "diet_clause": {
        "train": ["make it {diet}", "it has to be {diet}", "keep it {diet}", "{diet} only", "everything {diet}"],
        "dev": ["needs to be {diet}", "{diet} please"],
        "test": ["I eat {diet}", "must be {diet}", "stick to {diet}"],
    },
    "exclusion": {
        "train": ["without {x}", "no {x}", "skip the {x}", "leave out the {x}", "don't add {x}"],
        "dev": ["hold the {x}", "without any {x}"],
        "test": ["but I don't want any {x}", "minus the {x}", "I'm avoiding {x}", "nothing with {x}"],
    },
    "pantry": {
        "train": ["I already have {amt_x}", "I have {amt_x} at home", "got {amt_x} already", "I've got {amt_x}"],
        "dev": ["there's {amt_x} in my pantry", "I have {amt_x} left"],
        "test": ["{amt_x} is already in the kitchen", "I still have {amt_x}", "we have {amt_x} at home"],
    },
    "pantry_unknown": {
        "train": ["I already have some {x}", "I have {x} at home", "got some {x}"],
        "dev": ["there's a bit of {x} in my pantry"],
        "test": ["I still have some {x}", "we have {x} at home"],
    },
    "list_opener": {
        "train": ["buy {list}", "I need {list}", "add {list} to my cart", "get me {list}", "shopping list: {list}",
                  "please buy {list}"],
        "dev": ["pick up {list}", "I want {list}"],
        "test": ["could you order {list}", "please grab {list}", "order {list} for me", "I need to restock {list}"],
    },
    "revise_budget": {
        "train": ["change the budget to {budget}", "make the budget {budget}", "actually my budget is {budget}",
                  "set the budget to {budget}"],
        "dev": ["can we do it for {budget} instead"],
        "test": ["lower it to {budget}", "I only have {budget} now", "bring the total to {budget}"],
    },
    "revise_budget_vague": {
        "train": ["make it cheaper", "that's too expensive", "make it less expensive", "spend less"],
        "dev": ["can it cost less", "that's a bit much", "reduce the cost"],
        "test": ["too pricey, cut it down", "can you bring the price down", "this costs too much"],
    },
    "revise_servings": {
        "train": ["make it for {n} people", "change to {n} servings", "actually it's for {n}"],
        "dev": ["we're now {n}", "there will be {n} of us", "update it to {n} servings"],
        "test": ["scale it to {n} people", "now cooking for {n}", "it's {n} people now"],
    },
    "revise_exclusion": {
        "train": ["remove the {x}", "take out the {x}", "no {x} please"],
        "dev": ["drop the {x}"],
        "test": ["get rid of the {x}", "leave out the {x} after all"],
    },
    "revise_pantry": {
        "train": ["I also have {amt_x}", "oh and I have {amt_x}"],
        "dev": ["found {amt_x} in the fridge"],
        "test": ["turns out I have {amt_x}"],
    },
    "revise_diet": {
        "train": ["make it {diet}", "it needs to be {diet}"],
        "dev": ["switch to {diet}", "change it to {diet}", "go {diet} instead"],
        "test": ["can it be {diet}", "I'd prefer it {diet}", "turn it {diet}"],
    },
    "revise_item": {
        "train": ["also add {amt_x}", "add {amt_x} too"],
        "dev": ["throw in {amt_x}"],
        "test": ["and {amt_x} as well"],
    },
    "unsupported_frame": {
        "train": ["can you {act}", "{act} please", "I want you to {act}"],
        "dev": ["could you {act}", "please {act}", "I'd like you to {act}"],
        "test": ["would you be able to {act}", "help me {act}", "is it possible to {act}"],
    },
}
UNSUPPORTED_ACTS = {
    "train": ["tell me the weather in Lahore", "book a flight to Dubai", "tell me a joke", "solve this maths homework",
              "play some music", "deliver the groceries to my house", "find the nearest supermarket",
              "track my last order", "pay with my credit card", "tell me the calories in a banana",
              "compare prices at other stores", "set an alarm for 7 am", "translate this into French",
              "recommend a movie", "check if the shop is open", "write my essay", "order a pizza from a restaurant",
              "give me the news headlines", "show me a cooking video", "suggest a wine pairing",
              "call my mother", "book a table for dinner", "find a plumber", "tell me the cricket score",
              "send an email to my boss", "show my bank balance", "rate this recipe five stars",
              "convert dollars to euros", "explain photosynthesis", "remind me to drink water"],
    "dev": ["schedule a delivery slot", "tell me the time in London", "cancel my subscription",
            "find coupons for this store", "tell me who won the match yesterday", "book a taxi",
            "check my order status", "tell me how many calories are in rice"],
    "test": ["arrange home delivery for tonight", "find out the capital of Japan", "split the bill with my friend",
             "find out which store is cheapest", "write a poem about spring", "renew my passport",
             "find vegan restaurants nearby", "find out how much protein is in an egg"],
}
UNKNOWN_MEALS = {"train": ["lasagna", "biryani", "pizza", "pad thai", "paella"],
                 "dev": ["nihari", "ramen"], "test": ["haleem", "sushi", "chicken karahi"]}
CONNECTORS = [",", ",", "and", "."]
# Budgets are inclusive caps. Strict wording is never used when the budget equals the minimum cost.
STRICT_BUDGET = re.compile(r"\b(under|below)\b")
EXACT_BUDGET_DESIGNS = {"exact", "one_short", "pantry_full", "list_exact"}


# ---------------------------------------------------------------- vocabulary
def clean_name(name: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", name).strip().lower()


class Vocabulary:
    def __init__(self, catalog: dict, recipe_aliases: dict[str, list[str]], categories: dict[str, str]):
        self.catalog = catalog
        self.ingredients = {i["id"]: i for i in catalog["ingredients"]}
        self.recipes = {r["id"]: r for r in catalog["recipes"]}
        self.recipe_aliases = recipe_aliases
        self.surfaces = {}
        for iid, ing in self.ingredients.items():
            forms = [clean_name(ing["name"])] + [a.lower() for a in ing["aliases"]]
            self.surfaces[iid] = sorted({f for f in forms if f and not any(c.isdigit() for c in f)})
        missing = set(self.ingredients) - set(categories)
        if missing:
            raise ValueError(f"ingredients without a category: {sorted(missing)}")
        self.category = {i: categories[i] for i in self.ingredients}

    def ingredient_surface(self, rng, iid: str) -> str:
        return choice(rng, self.surfaces[iid])

    def recipe_surface(self, rng, rid: str) -> str:
        return choice(rng, self.recipe_aliases[rid])

    def display_name(self, iid: str) -> str:
        return clean_name(self.ingredients[iid]["name"])


# ---------------------------------------------------------------- gold requests
def amount_of(entry: dict) -> str | None:
    if entry.get("quantity") is None:
        return None
    return to_catalog_amount(Decimal(entry["quantity"]), entry["user_unit"])[1]


def unit_of(entry: dict) -> str:
    return USER_UNITS[entry["user_unit"]][0]


def clarification_prompt(kind: str | None, spec: dict, vocab: Vocabulary) -> str | None:
    if kind is None:
        return None
    if kind == "missing_budget":
        return "What is your budget in rupees?"
    if kind == "ambiguous_diet":
        return "Which dietary rule should I apply: vegetarian, vegan, gluten-free, dairy-free or nut-free?"
    if kind == "missing_pantry_quantity":
        entry = next(p for p in spec["pantry"] if p.get("quantity") is None)
        return f"How much {vocab.display_name(entry['ingredient_id'])} do you already have (in {unit_of(entry)})?"
    if kind == "missing_item_quantity":
        entry = next(p for p in spec["items"] if p.get("quantity") is None)
        return f"How much {vocab.display_name(entry['ingredient_id'])} do you need (in {unit_of(entry)})?"
    if kind == "missing_recipe":
        names = [vocab.recipe_aliases[r][0] for r in spec.get("suggestions", [])]
        listed = ", ".join(names[:-1]) + (" or " + names[-1] if len(names) > 1 else names[0] if names else "")
        return "Which dish would you like?" + (f" For example: {listed}." if names else "")
    raise ValueError(kind)


def build_gold(spec: dict, vocab: Vocabulary) -> dict:
    """The gold StructuredRequest (BUILD_PHASES section 4.3) for a spec."""
    if spec["intent"] == "unsupported":
        return {"request_id": spec["request_id"], "intent": "unsupported", "recipe_id": None, "servings": None,
                "items": [], "pantry": {}, "budget_minor": None, "currency": None, "diet": [], "exclusions": [],
                "user_id": spec.get("user_id"), "needs_clarification": False, "clarification_type": None,
                "clarification_prompt": None}
    items = [{"ingredient_id": e["ingredient_id"], "amount": amount_of(e), "unit": unit_of(e)}
             for e in spec.get("items", [])]
    pantry = {e["ingredient_id"]: amount_of(e) for e in spec.get("pantry", [])}
    kind = spec.get("clarification_type")
    return {
        "request_id": spec["request_id"],
        "intent": spec["intent"],
        "recipe_id": spec.get("recipe_id"),
        "servings": spec.get("servings"),
        "items": items,
        "pantry": dict(sorted(pantry.items())),
        "budget_minor": None if spec.get("budget") is None else spec["budget"] * 100,
        "currency": "PKR",
        "diet": sorted(spec.get("diet", [])),
        "exclusions": sorted(spec.get("exclusions", [])),
        "user_id": spec.get("user_id"),
        "needs_clarification": kind is not None,
        "clarification_type": kind,
        "clarification_prompt": clarification_prompt(kind, spec, vocab),
    }


def apply_revision(session: dict, spec: dict, vocab: Vocabulary) -> dict:
    """Merge a revision spec into the previous gold request."""
    rev = spec["revision"]
    merged = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
              for k, v in session.items()}
    merged.update({"request_id": spec["request_id"], "intent": "revise_basket", "needs_clarification": False,
                   "clarification_type": None, "clarification_prompt": None})
    kind = rev["type"]
    if kind == "budget":
        merged["budget_minor"] = rev["budget"] * 100
    elif kind == "budget_vague":
        merged.update(needs_clarification=True, clarification_type="missing_budget",
                      clarification_prompt=clarification_prompt("missing_budget", spec, vocab))
    elif kind == "servings":
        merged["servings"] = rev["servings"]
    elif kind == "exclusion":
        merged["exclusions"] = sorted(set(merged["exclusions"]) | {rev["ingredient_id"]})
    elif kind == "diet":
        merged["diet"] = sorted(set(merged["diet"]) | {rev["diet"]})
    elif kind == "pantry":
        merged["pantry"] = dict(sorted({**merged["pantry"], rev["entry"]["ingredient_id"]: amount_of(rev["entry"])}.items()))
    elif kind == "item":
        merged["items"] = merged["items"] + [{"ingredient_id": rev["entry"]["ingredient_id"],
                                              "amount": amount_of(rev["entry"]), "unit": unit_of(rev["entry"])}]
    else:
        raise ValueError(kind)
    return merged


# ---------------------------------------------------------------- rendering
def _amount_pieces(builder: TextBuilder, rng, entry: dict, label: str, vocab: Vocabulary) -> int:
    """Write '<qty> <unit> [of] <item>' and attach quantity and unit spans to the item."""
    surface = vocab.ingredient_surface(rng, entry["ingredient_id"])
    q_idx = u_idx = None
    if entry.get("quantity") is not None:
        quantity, user_unit = Decimal(entry["quantity"]), entry["user_unit"]
        if user_unit == "dozen" and quantity == 1 and rng.random() < 0.6:
            q_idx = builder.add("a", "QUANTITY", "1")
        else:
            q_idx = builder.add(number_surface(rng, quantity), "QUANTITY", format(quantity.normalize(), "f"))
        if user_unit != "piece":
            unit_word = choice(rng, unit_words(user_unit, quantity))
            glue = user_unit in {"g", "kg", "ml"} and unit_word in {"g", "kg", "ml"} and rng.random() < 0.4 \
                and builder.text[-1].isdigit()
            if glue:
                builder.text += unit_word
                start = len(builder.text) - len(unit_word)
                builder.spans.append({"label": "UNIT", "start": start, "end": len(builder.text), "text": unit_word,
                                      "value": user_unit, "attach_to": None})
                u_idx = len(builder.spans) - 1
            else:
                u_idx = builder.add(unit_word, "UNIT", user_unit)
            if rng.random() < 0.4:
                builder.add("of")
    x_idx = builder.add(surface, label, entry["ingredient_id"])
    for idx in (q_idx, u_idx):
        if idx is not None:
            builder.spans[idx]["attach_to"] = x_idx
    return x_idx


def _budget_pieces(builder: TextBuilder, rng, rupees: int) -> None:
    pieces, _ = budget_surface(rng, rupees)
    for text, label in pieces:
        builder.add(text, label, rupees if label == "BUDGET" else "PKR")


def _diet_piece(builder: TextBuilder, rng, diet: str | None) -> None:
    if diet is None:
        builder.add(choice(rng, AMBIGUOUS_DIET_FORMS), "DIET", "ambiguous")
    else:
        builder.add(choice(rng, DIET_FORMS[diet]), "DIET", diet)


def _servings_piece(builder: TextBuilder, rng, n: int) -> None:
    builder.add(number_surface(rng, Decimal(n)), "SERVINGS", n)


def _connector(builder: TextBuilder, rng) -> None:
    builder.add(choice(rng, CONNECTORS))


def _join_list(builder: TextBuilder, rng, entries: list[dict], vocab: Vocabulary) -> None:
    style = choice(rng, ["and", "comma"])
    for k, entry in enumerate(entries):
        if k:
            builder.add("and" if (k == len(entries) - 1 and style == "and") else ",")
        _amount_pieces(builder, rng, entry, "PRODUCT", vocab)


def render(spec: dict, rng, vocab: Vocabulary) -> dict:
    """Render one paraphrase of a spec from the pools of the spec's split."""
    split = spec["split"]
    pool = lambda name: POOLS[name][split]  # noqa: E731
    b = TextBuilder()
    clauses = []
    intent = spec["intent"]

    if intent == "unsupported":
        b.add_template(choice(rng, pool("unsupported_frame")), {"act": lambda bb: [bb.add(w) for w in spec["act"].split()]})
        return b.finish()

    if intent == "revise_basket":
        rev = spec["revision"]
        name = {"budget": "revise_budget", "budget_vague": "revise_budget_vague", "servings": "revise_servings",
                "exclusion": "revise_exclusion", "pantry": "revise_pantry", "diet": "revise_diet",
                "item": "revise_item"}[rev["type"]]
        b.add_template(choice(rng, pool(name)), {
            "budget": lambda bb: _budget_pieces(bb, rng, rev["budget"]),
            "n": lambda bb: _servings_piece(bb, rng, rev.get("servings", 0)),
            "x": lambda bb: bb.add(vocab.ingredient_surface(rng, rev.get("ingredient_id", "")), "EXCLUSION",
                                   rev.get("ingredient_id")),
            "amt_x": lambda bb: _amount_pieces(bb, rng, rev["entry"], "PANTRY" if rev["type"] == "pantry" else "PRODUCT",
                                               vocab),
            "diet": lambda bb: _diet_piece(bb, rng, rev.get("diet")),
        })
        return b.finish()

    if intent == "plan_meal":
        diet_inline = spec.get("diet") and rng.random() < 0.4 and spec["meal_kind"] == "recipe"
        if spec["meal_kind"] == "broad":
            diet_adj = spec["diet"][0] if spec.get("diet") else None
            template = choice(rng, pool("broad_opener"))
            parts = template.split("{diet_adj}")
            for k, part in enumerate(parts):
                if k and diet_adj:
                    _diet_piece(b, rng, diet_adj)
                for word in part.split():
                    b.add(word)
            diet_done = bool(diet_adj)
        else:
            def meal(bb):
                if diet_inline:
                    _diet_piece(bb, rng, spec["diet"][0])
                if spec["meal_kind"] == "unknown":
                    bb.add(spec["unknown_meal"], "MEAL", None)
                else:
                    bb.add(vocab.recipe_surface(rng, spec["recipe_id"]), "MEAL", spec["recipe_id"])
            b.add_template(choice(rng, pool("meal_opener")), {"meal": meal})
            diet_done = diet_inline
        if spec.get("servings") is not None:
            clauses.append(("servings", lambda bb: bb.add_template(choice(rng, pool("servings")),
                                                                   {"n": lambda x: _servings_piece(x, rng, spec["servings"])})))
        remaining_diets = [] if diet_done else list(spec.get("diet", []))
        if len(spec.get("diet", [])) > 1 and diet_done:
            remaining_diets = spec["diet"][1:]
    else:  # build_grocery_list
        b.add_template(choice(rng, pool("list_opener")), {"list": lambda bb: _join_list(bb, rng, spec["items"], vocab)})
        remaining_diets = list(spec.get("diet", []))

    if spec.get("budget") is not None:
        templates = pool("budget")
        if spec.get("design") in EXACT_BUDGET_DESIGNS:
            # The budget equals the minimum cost, so strict wording ("under", "below") would contradict the label.
            templates = [t for t in templates if not STRICT_BUDGET.search(t)]
        clauses.append(("budget", lambda bb: bb.add_template(choice(rng, templates),
                                                             {"budget": lambda x: _budget_pieces(x, rng, spec["budget"])})))
    if spec.get("budget_vague"):
        clauses.append(("vague", lambda bb: [bb.add(w) for w in choice(rng, pool("vague_budget")).split()]))
    for d in remaining_diets:
        if rng.random() < 0.3:
            clauses.append(("diet", lambda bb, d=d: bb.add(choice(rng, DIET_NEGATION_FORMS[d]), "DIET", d)))
        else:
            clauses.append(("diet", lambda bb, d=d: bb.add_template(choice(rng, pool("diet_clause")),
                                                                    {"diet": lambda x: _diet_piece(x, rng, d)})))
    if spec.get("diet_ambiguous"):
        clauses.append(("diet", lambda bb: bb.add_template(choice(rng, pool("diet_clause")),
                                                           {"diet": lambda x: _diet_piece(x, rng, None)})))
    for x in spec.get("exclusions", []):
        clauses.append(("excl", lambda bb, x=x: bb.add_template(choice(rng, pool("exclusion")), {
            "x": lambda y: y.add(vocab.ingredient_surface(rng, x), "EXCLUSION", x)})))
    for entry in spec.get("pantry", []):
        if entry.get("quantity") is None:
            clauses.append(("pantry", lambda bb, e=entry: bb.add_template(choice(rng, pool("pantry_unknown")), {
                "x": lambda y: y.add(vocab.ingredient_surface(rng, e["ingredient_id"]), "PANTRY", e["ingredient_id"])})))
        else:
            clauses.append(("pantry", lambda bb, e=entry: bb.add_template(choice(rng, pool("pantry")), {
                "amt_x": lambda y: _amount_pieces(y, rng, e, "PANTRY", vocab)})))
    for _, write in shuffled(rng, clauses):
        _connector(b, rng)
        write(b)
    return b.finish()


# ---------------------------------------------------------------- spec helpers
def min_cost(catalog: dict, request: dict) -> int | None:
    probe = {**request, "budget_minor": None, "needs_clarification": False, "intent": "plan_meal"}
    result = check_feasibility(probe, catalog)
    return result["min_cost_minor"] if result["label"] == "feasible" else None


def round_up(value: int, step: int) -> int:
    return -(-value // step) * step


def nice_quantity(rng, unit: str, required: Decimal, mode: str) -> tuple[Decimal, str] | None:
    """A pantry (quantity, user unit) that partially or fully covers a requirement."""
    if unit == "piece":
        req = int(required.to_integral_value(rounding="ROUND_CEILING"))
        if mode == "full":
            return Decimal(req + (1 if rng.random() < 0.3 else 0)), "piece"
        return (Decimal(max(1, req // 2)), "piece") if req >= 2 else None
    if unit == "ml" and required <= 30:
        grid = [(Decimal(n), "tsp") for n in (1, 2, 3)] + [(Decimal(n), "tbsp") for n in (1, 2)]
    elif unit == "ml":
        grid = [(Decimal(n), "ml") for n in (100, 150, 200, 250, 300, 500)] + [(Decimal(n), "l") for n in (1, 2)]
    else:
        grid = [(Decimal(n), "g") for n in (50, 100, 150, 200, 250, 300, 400, 500, 750)] + \
               [(Decimal(n), "kg") for n in (1, 2)]
    values = [(q, u, Decimal(to_catalog_amount(q, u)[1])) for q, u in grid]
    if mode == "full":
        ok = [v for v in values if v[2] >= required]
        return (min(ok, key=lambda v: v[2])[:2]) if ok else None
    ok = [v for v in values if Decimal("0.25") * required <= v[2] < Decimal("0.85") * required]
    return choice(rng, ok)[:2] if ok else None


def list_quantity(rng, iid: str, vocab: Vocabulary) -> tuple[Decimal, str]:
    units = vocab.ingredients[iid]["supported_units"]
    unit = units[0]
    if unit == "piece":
        if iid == "egg" and rng.random() < 0.5:
            return Decimal(choice(rng, [1, 2])), "dozen"
        return Decimal(choice(rng, [1, 2, 3, 4, 6])), "piece"
    if unit == "ml":
        return choice(rng, [(Decimal(250), "ml"), (Decimal(500), "ml"), (Decimal(1), "l"), (Decimal(2), "l")])
    return choice(rng, [(Decimal(250), "g"), (Decimal(500), "g"), (Decimal(1), "kg"), (Decimal(2), "kg"),
                        (Decimal(1), "lb")])


LIST_CATEGORIES = {"produce", "dairy", "meat", "fish", "grain", "egg", "bakery", "canned", "oil", "sauce",
                   "pantry", "protein", "dairy_alternative"}
# Ingredients whose catalog unit does not read naturally in a shopping list
# (a "piece" of cilantro is a bunch; of garlic, a clove; of green onion, a stalk).
LIST_EXCLUDED = {"cilantro", "garlic", "green_onion", "water", "lime_juice", "lemon_juice", "parsley",
                 "baking_powder", "cornstarch"}
# Main ingredients are never excluded: "lamb chops without lamb" is not a request people make.
MAIN_CATEGORIES = {"meat", "fish", "grain", "egg", "bakery"}


def excludable(vocab: "Vocabulary", recipe_id: str) -> list[str]:
    """Recipe ingredients a user might plausibly ask to leave out."""
    names = " ".join([vocab.recipes[recipe_id]["name"].lower()] + vocab.recipe_aliases[recipe_id])
    out = []
    for line in vocab.recipes[recipe_id]["ingredients"]:
        iid = line["ingredient_id"]
        if vocab.category[iid] in MAIN_CATEGORIES or iid in out:
            continue
        if any(word in names for form in vocab.surfaces[iid] for word in form.split() if len(word) > 3):
            continue
        out.append(iid)
    return out
