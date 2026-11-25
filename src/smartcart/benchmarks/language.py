"""Surface realisation helpers for generated requests: tokens, spans, numbers, units.

Randomness uses only ``random.Random.random()``, whose sequence Python guarantees to
stay the same across versions for a given seed. ``choice`` and ``shuffle`` are
re-implemented on top of it for the same reason.
"""

from __future__ import annotations

import re
from decimal import Decimal

from smartcart.validation.feasibility import quantize_amount

TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[A-Za-z]+(?:['’-][A-Za-z]+)*|[^\w\s]")
PUNCT_NO_SPACE_BEFORE = {",", ".", "?", "!", ":", ";"}

NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
                9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}

# User unit -> (catalog unit, factor to the catalog unit, surface synonyms).
# Factors are NIST SP 811 values, as in configs/catalog_build.json.
USER_UNITS = {
    "g": ("g", Decimal("1"), ["g", "gram", "gm"], ["g", "grams", "gm"]),
    "kg": ("g", Decimal("1000"), ["kg", "kilo", "kilogram"], ["kg", "kilos", "kilograms"]),
    "lb": ("g", Decimal("453.59237"), ["lb", "pound"], ["lb", "lbs", "pounds"]),
    "ml": ("ml", Decimal("1"), ["ml"], ["ml", "millilitres"]),
    "l": ("ml", Decimal("1000"), ["litre", "liter", "l"], ["litres", "liters", "l"]),
    "tsp": ("ml", Decimal("4.928922"), ["tsp", "teaspoon"], ["tsp", "teaspoons"]),
    "tbsp": ("ml", Decimal("14.78676"), ["tbsp", "tablespoon"], ["tbsp", "tablespoons"]),
    "cup": ("ml", Decimal("236.5882"), ["cup"], ["cups"]),
    "piece": ("piece", Decimal("1"), [""], [""]),
    "dozen": ("piece", Decimal("12"), ["dozen"], ["dozen"]),
}


def unit_words(user_unit: str, quantity: Decimal) -> list[str]:
    """Singular unit words for exactly one, plural forms otherwise."""
    return USER_UNITS[user_unit][2] if quantity == 1 else USER_UNITS[user_unit][3]

CURRENCY_FORMS = ["Rs", "Rs.", "rupees", "PKR", "rs"]

# Adjective forms fit "make it ___" and "___ pasta"; negation forms stand alone as a clause.
# A negated diet category is a DIET span that includes the cue ("no dairy"); a negated
# ingredient is an EXCLUSION span on the ingredient only ("no [cheddar]").
DIET_FORMS = {
    "vegetarian": ["vegetarian", "veggie", "meat-free"],
    "vegan": ["vegan", "plant-based"],
    "gluten_free": ["gluten-free", "gluten free"],
    "dairy_free": ["dairy-free", "dairy free", "non-dairy"],  # not "lactose-free": lactose-free milk is dairy
    "nut_free": ["nut-free", "nut free"],
}
DIET_NEGATION_FORMS = {
    "vegetarian": ["no meat"],
    "vegan": ["no animal products"],
    "gluten_free": ["no gluten", "without gluten"],
    "dairy_free": ["no dairy", "without dairy"],
    "nut_free": ["no nuts", "without nuts"],
}
AMBIGUOUS_DIET_FORMS = ["healthy", "light", "low-carb", "keto", "clean", "diet-friendly"]


def choice(rng, seq):
    if not seq:
        raise ValueError("empty choice")
    return seq[int(rng.random() * len(seq))]


def shuffled(rng, seq):
    items = list(seq)
    for i in range(len(items) - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        items[i], items[j] = items[j], items[i]
    return items


def tokenize(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in TOKEN.finditer(text)]


class TextBuilder:
    """Append text pieces; labelled pieces become character spans."""

    def __init__(self):
        self.text = ""
        self.spans: list[dict] = []

    def add(self, piece: str, label: str | None = None, value=None, attach_to: int | None = None) -> int | None:
        if not piece:
            return None
        if self.text and piece not in PUNCT_NO_SPACE_BEFORE and not piece.startswith(tuple(PUNCT_NO_SPACE_BEFORE)):
            self.text += " "
        start = len(self.text)
        self.text += piece
        if label is None:
            return None
        self.spans.append({"label": label, "start": start, "end": len(self.text), "text": piece,
                           "value": value, "attach_to": attach_to})
        return len(self.spans) - 1

    def add_template(self, template: str, fillers: dict) -> dict:
        """Render 'text {slot} text'; each filler is a callable that writes its own pieces."""
        result = {}
        for part in re.split(r"(\{[a-z_]+\})", template):
            if not part:
                continue
            if part.startswith("{"):
                result[part[1:-1]] = fillers[part[1:-1]](self)
            else:
                for word in part.split():
                    self.add(word)
        return result

    def finish(self) -> dict:
        text = self.text[0].upper() + self.text[1:] if self.text else self.text
        tokens = tokenize(text)
        tags = ["O"] * len(tokens)
        for span in self.spans:
            inside = [i for i, (_, s, e) in enumerate(tokens) if s < span["end"] and e > span["start"]]
            if not inside or tokens[inside[0]][1] != span["start"] or tokens[inside[-1]][2] != span["end"] \
                    or any(tokens[i][1] < span["start"] or tokens[i][2] > span["end"] for i in inside):
                raise ValueError(f"span {span} does not align with tokens")
            for k, i in enumerate(inside):
                if tags[i] != "O":
                    raise ValueError(f"overlapping spans at token {i}")
                tags[i] = ("B-" if k == 0 else "I-") + span["label"]
        spans = [{**s, "text": text[s["start"]:s["end"]]} for s in self.spans]
        return {"text": text, "tokens": [t for t, _, _ in tokens], "bio_tags": tags, "spans": spans}


def number_surface(rng, value: Decimal, allow_words: bool = True) -> str:
    if value == value.to_integral_value():
        n = int(value)
        if allow_words and n in NUMBER_WORDS and rng.random() < 0.35:
            return NUMBER_WORDS[n]
        return str(n)
    return format(value.normalize(), "f")


def to_catalog_amount(quantity: Decimal, user_unit: str) -> tuple[str, str]:
    unit, factor = USER_UNITS[user_unit][:2]
    return unit, format(quantize_amount(quantity * factor), "f")


def budget_surface(rng, rupees: int) -> tuple[list[tuple[str, str | None]], bool]:
    """Return pieces [(text, label)] for a budget; label is BUDGET or CURRENCY."""
    forms = [str(rupees), f"{rupees:,}"]
    if rupees % 1000 == 0:
        forms.append(f"{rupees // 1000}k")
    elif rupees % 500 == 0 and rupees > 1000:
        forms.append(f"{rupees / 1000:g}k")
    words = {1000: "one thousand", 1500: "fifteen hundred", 2000: "two thousand", 2500: "twenty-five hundred",
             3000: "three thousand", 5000: "five thousand", 4000: "four thousand", 1200: "twelve hundred"}
    if rupees in words:
        forms.append(words[rupees])
    number = choice(rng, forms)
    style = choice(rng, ["before", "after", "after", "none", "slash"])
    currency = choice(rng, CURRENCY_FORMS)
    if style == "before":
        return [(currency, "CURRENCY"), (number, "BUDGET")], True
    if style == "after":
        return [(number, "BUDGET"), ("rupees" if currency in {"Rs", "Rs.", "rs"} else currency, "CURRENCY")], True
    if style == "slash" and number[0].isdigit() and not number.endswith("k"):
        return [(currency, "CURRENCY"), (number + "/-", "BUDGET")], True
    return [(number, "BUDGET")], False
