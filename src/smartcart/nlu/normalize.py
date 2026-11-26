"""Normalise tagged spans into typed values (Phase 6, also usable by any span tagger).

A tagger only marks *where* a slot is. This module gives each span its value:

- MEAL -> recipe ID (``None`` for a dish outside the catalog, which triggers ``missing_recipe``);
- PRODUCT / PANTRY / EXCLUSION -> canonical ingredient ID;
- BUDGET -> rupees, SERVINGS -> integer, QUANTITY -> decimal string, UNIT -> user unit,
  CURRENCY -> "PKR", DIET -> diet rule or "ambiguous".

Lookups go exact match first, then simple plural variants (already in the lexicon), then a
close spelling match (``difflib`` ratio >= ``FUZZY_CUTOFF``) so misspellings still resolve.
QUANTITY and UNIT spans attach to the next PRODUCT or PANTRY span when only quantity and
unit spans lie between them, which is how quantities are written ("2 kg of rice").
"""

from __future__ import annotations

import difflib
from decimal import Decimal

from smartcart.benchmarks.language import tokenize
from smartcart.nlu.lexicon import UNIT_WORDS, Lexicon, key_of, parse_number

FUZZY_CUTOFF = 0.85
ITEM_LABELS = {"PRODUCT", "PANTRY"}


class SpanNormalizer:
    def __init__(self, lexicon: Lexicon):
        self.lex = lexicon
        self._ingredient_forms = {" ".join(k): v for k, v in lexicon.ingredient_keys.items()}
        self._meal_forms = {" ".join(k): v for k, v in lexicon.meal_keys.items()}
        self._diet_forms = {" ".join(k): v for k, v in lexicon.diet_keys.items()}

    @staticmethod
    def _lookup(text: str, table: dict, forms: dict):
        key = key_of(text)
        if key in table:
            return table[key]
        match = difflib.get_close_matches(" ".join(key), list(forms), n=1, cutoff=FUZZY_CUTOFF)
        return forms[match[0]] if match else None

    @staticmethod
    def _number(text: str):
        tokens = tokenize(text)
        if not tokens:
            return None
        parsed = parse_number(tokens, 0)
        if parsed is None and tokens[0][0].lower() == "a":
            return Decimal(1)
        return parsed[0] if parsed else None

    def value(self, label: str, text: str):
        if label == "MEAL":
            return self._lookup(text, self.lex.meal_keys, self._meal_forms)
        if label in {"PRODUCT", "PANTRY", "EXCLUSION"}:
            return self._lookup(text, self.lex.ingredient_keys, self._ingredient_forms)
        if label == "DIET":
            return self._lookup(text, self.lex.diet_keys, self._diet_forms) or "ambiguous"
        if label == "CURRENCY":
            return "PKR"
        if label == "UNIT":
            return UNIT_WORDS.get(text.lower().strip())
        number = self._number(text)
        if number is None:
            return None
        if label == "BUDGET":
            return int(number) if number == int(number) else number
        if label == "SERVINGS":
            return int(number) if number == int(number) and number > 0 else None
        if label == "QUANTITY":
            return format(number.normalize(), "f")
        return None

    def normalise(self, spans: list[dict]) -> list[dict]:
        """Fill ``value`` and ``attach_to`` for spans given as (label, start, end, text)."""
        out = [{**s, "value": self.value(s["label"], s["text"]), "attach_to": None} for s in spans]
        for i, span in enumerate(out):
            if span["label"] not in {"QUANTITY", "UNIT"}:
                continue
            for j in range(i + 1, len(out)):
                if out[j]["label"] in ITEM_LABELS:
                    span["attach_to"] = j
                    break
                if out[j]["label"] not in {"QUANTITY", "UNIT"}:
                    break
        return out
