"""Dictionaries and number rules for the rule-based (E0) slot extractor.

Everything here is either catalog knowledge (ingredient names and reviewed aliases,
recipe aliases) or a general-purpose word list (units, currencies, number words,
negation and pantry cues, diet words). The cue lists were written from the training and
validation examples plus common English usage. They are not tuned on the test split.
"""

from __future__ import annotations

import csv
import re
from decimal import Decimal
from pathlib import Path

from smartcart.benchmarks.language import tokenize

# User unit word -> canonical user unit. Conversion factors are in USER_UNIT_FACTORS.
UNIT_WORDS = {
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g", "gramme": "g", "grammes": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l", "ltr": "l",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "cup": "cup", "cups": "cup",
    "dozen": "dozen",
}
# User unit -> (catalog unit, factor). NIST SP 811 values, as in configs/catalog_build.json.
USER_UNIT_FACTORS = {
    "g": ("g", Decimal("1")), "kg": ("g", Decimal("1000")), "lb": ("g", Decimal("453.59237")),
    "ml": ("ml", Decimal("1")), "l": ("ml", Decimal("1000")), "tsp": ("ml", Decimal("4.928922")),
    "tbsp": ("ml", Decimal("14.78676")), "cup": ("ml", Decimal("236.5882")),
    "piece": ("piece", Decimal("1")), "dozen": ("piece", Decimal("12")),
}

CURRENCY_WORDS = {"rs", "rupees", "rupee", "pkr"}

ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
        "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000}

# A bare number that is not a quantity or budget is read as servings if it is a small integer.
MAX_SERVINGS = 30
MIN_BUDGET_RUPEES = 100

NEGATION_CUES = {"no", "not", "without", "skip", "don't", "dont", "hold", "remove", "drop", "exclude",
                 "excluding", "omit", "avoid", "avoiding", "never", "nothing", "none", "out"}
PANTRY_CUES = {"have", "got", "pantry", "home", "left", "already", "fridge", "kitchen", "still", "found"}
CLAUSE_BREAKS = {",", ".", ";", "!", "?", "and", "but"}

# Diet words. A negated diet category is one DIET span including the cue ("no dairy").
DIET_SURFACES = {
    "vegetarian": ["vegetarian", "veggie", "veg", "meat-free", "meat free", "meatless", "no meat", "without meat"],
    "vegan": ["vegan", "plant-based", "plant based", "no animal products"],
    "gluten_free": ["gluten-free", "gluten free", "no gluten", "without gluten"],
    "dairy_free": ["dairy-free", "dairy free", "non-dairy", "no dairy", "without dairy"],
    "nut_free": ["nut-free", "nut free", "no nuts", "without nuts"],
}
# Words that ask for a diet without saying which rule applies.
AMBIGUOUS_DIET_SURFACES = ["healthy", "light", "low-carb", "low carb", "keto", "clean", "diet-friendly",
                           "low-fat", "low fat", "paleo"]
# Cost wording without a number.
VAGUE_BUDGET_TOKENS = {"cheap", "cheaper", "cheapest", "expensive", "pricey", "affordable", "inexpensive",
                       "costly"}
VAGUE_BUDGET_PHRASES = ["on a budget", "budget friendly", "budget-friendly", "cost less", "costs less",
                        "spend less", "too much", "bit much", "reduce the cost", "lower the cost"]


def clean_name(name: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", name).strip().lower()


def key_of(phrase: str) -> tuple[str, ...]:
    return tuple(t.lower() for t, _, _ in tokenize(phrase))


def plural_variants(form: str) -> set[str]:
    """Simple singular/plural variants of the last word ("onion" <-> "onions")."""
    head, _, last = form.rpartition(" ")
    prefix = head + " " if head else ""
    out = set()
    if last.endswith("ies") and len(last) > 4:
        out.add(last[:-3] + "y")
    elif last.endswith(("oes", "ches", "shes", "xes")):
        out.add(last[:-2])
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
        out.add(last[:-1])
    elif last.endswith("y") and len(last) > 3 and last[-2] not in "aeiou":
        out.add(last[:-1] + "ies")
    elif last.endswith(("o", "ch", "sh", "x")):
        out.add(last + "es")
    else:
        out.add(last + "s")
    return {prefix + w for w in out}


def read_recipe_aliases(path: Path) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            aliases.setdefault(row["recipe_id"], []).append(row["alias"])
    return aliases


class Lexicon:
    """Token-sequence gazetteers over catalog ingredients, recipes and diet words."""

    def __init__(self, catalog: dict, recipe_aliases: dict[str, list[str]]):
        self.catalog = catalog
        self.ingredients = {i["id"]: i for i in catalog["ingredients"]}
        self.recipes = {r["id"]: r for r in catalog["recipes"]}
        self.ingredient_keys = self._ingredient_table()
        self.meal_keys = self._unique({rid: [clean_name(self.recipes[rid]["name"])] + list(recipe_aliases.get(rid, []))
                                       for rid in self.recipes})
        diet = {}
        for value, forms in DIET_SURFACES.items():
            for form in forms:
                diet[key_of(form)] = value
        for form in AMBIGUOUS_DIET_SURFACES:
            diet[key_of(form)] = "ambiguous"
        self.diet_keys = diet
        self.vague_budget_keys = {key_of(p) for p in VAGUE_BUDGET_PHRASES}
        self.max_len = max(len(k) for table in (self.ingredient_keys, self.meal_keys, self.diet_keys) for k in table)

    @staticmethod
    def _unique(forms_by_id: dict[str, list[str]]) -> dict[tuple[str, ...], str]:
        owners: dict[tuple[str, ...], set[str]] = {}
        for value, forms in forms_by_id.items():
            for form in forms:
                key = key_of(form.lower())
                if key:
                    owners.setdefault(key, set()).add(value)
        return {k: next(iter(v)) for k, v in owners.items() if len(v) == 1}

    def _ingredient_table(self) -> dict[tuple[str, ...], str]:
        exact = {iid: [clean_name(i["name"])] + [a.lower() for a in i["aliases"]]
                 for iid, i in self.ingredients.items()}
        exact = {iid: [f for f in forms if f and not any(c.isdigit() for c in f)] for iid, forms in exact.items()}
        table = self._unique(exact)
        variants = self._unique({iid: sorted({v for f in forms for v in plural_variants(f)})
                                 for iid, forms in exact.items()})
        for key, iid in variants.items():
            table.setdefault(key, iid)  # listed forms win over generated variants
        return table

    def ingredient_query(self, ingredient_id: str) -> str:
        return clean_name(self.ingredients[ingredient_id]["name"])

    def first_unit(self, ingredient_id: str) -> str:
        return self.ingredients[ingredient_id]["supported_units"][0]


def parse_number(tokens: list[tuple[str, int, int]], i: int) -> tuple[Decimal, int, bool] | None:
    """Parse a number starting at token i. Returns (value, end index, has_budget_suffix)."""
    word = tokens[i][0].lower()
    if word[0].isdigit():
        raw = word.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", word) else word.replace(",", ".")
        try:
            value = Decimal(raw)
        except ArithmeticError:
            return None
        j, suffix = i + 1, False
        if j < len(tokens) and tokens[j][0].lower() == "k" and tokens[j][1] == tokens[i][2]:
            value, j, suffix = value * 1000, j + 1, True
        if j + 1 < len(tokens) and tokens[j][0] == "/" and tokens[j + 1][0] == "-" and tokens[j][1] == tokens[j - 1][2]:
            j, suffix = j + 2, True
        return value, j, suffix
    if word == "a" and i + 1 < len(tokens) and tokens[i + 1][0].lower() == "dozen":
        return Decimal(1), i + 1, False
    total, current, j = 0, 0, i
    seen = False
    while j < len(tokens):
        w = tokens[j][0].lower()
        parts = w.split("-")
        if w in ONES:
            current += ONES[w]
        elif w in TENS:
            current += TENS[w]
        elif len(parts) == 2 and parts[0] in TENS and parts[1] in ONES and 0 < ONES[parts[1]] < 10:
            current += TENS[parts[0]] + ONES[parts[1]]
        elif w in SCALES and seen:
            if SCALES[w] == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * 1000
                current = 0
        else:
            break
        seen = True
        j += 1
    if not seen:
        return None
    return Decimal(total + current), j, False
