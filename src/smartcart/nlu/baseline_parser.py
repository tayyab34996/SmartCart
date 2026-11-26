"""E0 baseline parser: TF-IDF + LinearSVC intent and rule/dictionary slots (Phase 5, D3).

The parser turns a user message into a StructuredRequest (BUILD_PHASES section 4.3):

1. **Intent.** A scikit-learn ``Pipeline`` of ``TfidfVectorizer`` and ``LinearSVC``,
   trained only on the 600 training examples of ``data/annotations/nlu.jsonl``.
2. **Slots.** Longest-match gazetteers over catalog ingredient names and aliases, recipe
   aliases and diet words, then number rules:
   - a number followed by a unit word and/or an ingredient is a QUANTITY (with UNIT),
     attached to that ingredient;
   - a number next to a currency word, with a ``k`` or ``/-`` suffix, or of at least
     100 is a BUDGET (rupees);
   - any other integer up to 30 is SERVINGS.
   An ingredient mention takes its role from cue words in its clause: a negation cue
   before it makes an EXCLUSION, a pantry cue ("have", "got", "pantry", ...) makes a
   PANTRY item, otherwise it is a PRODUCT in grocery lists and revisions.
3. **Normalisation.** Amounts are converted to the catalog unit, budgets to minor units,
   and revisions are merged into the previous request (``session``).
4. **Clarification gate.** Rules ask for a missing recipe, an ambiguous diet, a vague
   budget, or a missing pantry or item quantity. There is no confidence gating in E0.
"""

from __future__ import annotations

from decimal import Decimal

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from smartcart.benchmarks.language import tokenize
from smartcart.nlu.lexicon import (
    CLAUSE_BREAKS, CURRENCY_WORDS, MAX_SERVINGS, MIN_BUDGET_RUPEES, NEGATION_CUES, PANTRY_CUES, UNIT_WORDS,
    USER_UNIT_FACTORS, VAGUE_BUDGET_TOKENS, Lexicon, parse_number,
)
from smartcart.validation.feasibility import check_feasibility, quantize_amount

INTENTS = ("build_grocery_list", "plan_meal", "revise_basket", "unsupported")
ITEM_INTENTS = {"build_grocery_list", "revise_basket"}
DIET_PROMPT = "Which dietary rule should I apply: vegetarian, vegan, gluten-free, dairy-free or nut-free?"


def suggest_recipes(request: dict, catalog: dict, limit: int = 3) -> list[str]:
    """Up to ``limit`` recipes feasible under the request's diet, budget and servings, cheapest first."""
    ranked = []
    for rid in sorted(r["id"] for r in catalog["recipes"]):
        probe = {"intent": "plan_meal", "recipe_id": rid, "servings": request.get("servings"), "items": [],
                 "pantry": {}, "budget_minor": request.get("budget_minor"), "diet": request.get("diet", []),
                 "exclusions": []}
        result = check_feasibility(probe, catalog)
        if result["label"] == "feasible":
            ranked.append((result["min_cost_minor"], rid))
    return [rid for _, rid in sorted(ranked)[:limit]]


# ---------------------------------------------------------------- intent
def build_intent_pipeline(config: dict) -> Pipeline:
    """TF-IDF features ("word", "char_wb" or "word+char") and a LinearSVC in one Pipeline."""
    vec = config.get("vectorizer", {})
    clf = config.get("classifier", {})

    def tfidf(analyzer: str, ngram_range) -> TfidfVectorizer:
        return TfidfVectorizer(lowercase=True, analyzer=analyzer, ngram_range=tuple(ngram_range),
                               sublinear_tf=vec.get("sublinear_tf", True), min_df=vec.get("min_df", 1))

    analyzer = vec.get("analyzer", "word")
    if analyzer == "word+char":
        features = FeatureUnion([("word", tfidf("word", vec.get("word_ngram_range", (1, 2)))),
                                 ("char", tfidf("char_wb", vec.get("char_ngram_range", (2, 4))))])
    else:
        features = tfidf(analyzer, vec.get("ngram_range", (1, 2)))
    return Pipeline([("tfidf", features),
                     ("svc", LinearSVC(C=clf.get("C", 1.0), random_state=clf.get("random_state", 0)))])


def train_intent_model(texts: list[str], labels: list[str], config: dict) -> Pipeline:
    model = build_intent_pipeline(config)
    model.fit(texts, labels)
    return model


# ---------------------------------------------------------------- slots
def _span(tokens, i: int, j: int, label: str, value, text: str) -> dict:
    start, end = tokens[i][1], tokens[j - 1][2]
    return {"label": label, "start": start, "end": end, "text": text[start:end], "value": value, "attach_to": None}


def _clause(low: list[str], i: int, j: int) -> tuple[list[str], list[str]]:
    lb = i
    while lb > 0 and low[lb - 1] not in CLAUSE_BREAKS:
        lb -= 1
    rb = j
    while rb < len(low) and low[rb] not in CLAUSE_BREAKS:
        rb += 1
    return low[lb:i], low[j:rb]


def _is_pantry_cue(token: str) -> bool:
    return token in PANTRY_CUES or token.endswith(("'ve", "’ve"))


class RuleSlotExtractor:
    def __init__(self, lexicon: Lexicon):
        self.lex = lexicon

    def _gazetteer(self, low: list[str], intent: str) -> list[dict]:
        order = ("diet", "ingredient", "meal") if intent in ITEM_INTENTS else ("diet", "meal", "ingredient")
        tables = {"diet": self.lex.diet_keys, "meal": self.lex.meal_keys, "ingredient": self.lex.ingredient_keys}
        mentions, i = [], 0
        while i < len(low):
            found = None
            for length in range(min(self.lex.max_len, len(low) - i), 0, -1):
                key = tuple(low[i:i + length])
                kind = next((k for k in order if key in tables[k]), None)
                if kind:
                    found = {"kind": kind, "i": i, "j": i + length, "value": tables[kind][key]}
                    break
            if found:
                mentions.append(found)
                i = found["j"]
            else:
                i += 1
        return mentions

    def vague_budget(self, low: list[str]) -> bool:
        if any(t in VAGUE_BUDGET_TOKENS for t in low):
            return True
        return any(tuple(low[i:i + len(k)]) == k for k in self.lex.vague_budget_keys for i in range(len(low)))

    def extract(self, text: str, intent: str) -> list[dict]:
        """Labelled character spans (gold annotation format) for one message."""
        if intent == "unsupported":
            return []
        tokens = tokenize(text)
        low = [t.lower() for t, _, _ in tokens]
        mentions = self._gazetteer(low, intent)
        owned = [False] * len(tokens)
        for m in mentions:
            for k in range(m["i"], m["j"]):
                owned[k] = True
        at = {m["i"]: m for m in mentions}
        spans: list[dict] = []
        attachments: list[tuple[int, dict]] = []  # (span index, target mention)

        i = 0
        while i < len(tokens):
            parsed = None if owned[i] else parse_number(tokens, i)
            if not parsed or any(owned[k] for k in range(i, parsed[1])):
                i += 1
                continue
            value, j, suffix = parsed
            unit_j = j if j < len(tokens) and not owned[j] and low[j] in UNIT_WORDS else None
            after = unit_j + 1 if unit_j is not None else j
            if unit_j is not None and after < len(tokens) and low[after] == "of":
                after += 1
            target = at.get(after) if (after < len(tokens) and at.get(after, {}).get("kind") == "ingredient") else None
            if unit_j is not None or target is not None:
                q = len(spans)
                spans.append(_span(tokens, i, j, "QUANTITY", format(value.normalize(), "f"), text))
                if unit_j is not None:
                    spans.append(_span(tokens, unit_j, unit_j + 1, "UNIT", UNIT_WORDS[low[unit_j]], text))
                    owned[unit_j] = True
                if target is not None:
                    attachments.extend((k, target) for k in range(q, len(spans)))
            else:
                currency = self._currency(tokens, low, owned, i, j)
                if currency or suffix or value >= MIN_BUDGET_RUPEES:
                    spans.append(_span(tokens, i, j, "BUDGET", int(value) if value == int(value) else value, text))
                    for a, b in currency:
                        spans.append(_span(tokens, a, b, "CURRENCY", "PKR", text))
                        for k in range(a, b):
                            owned[k] = True
                elif value == int(value) and 0 < value <= MAX_SERVINGS:
                    spans.append(_span(tokens, i, j, "SERVINGS", int(value), text))
            for k in range(i, j):
                owned[k] = True
            i = j

        roles = {}
        for m in mentions:
            if m["kind"] == "meal":
                roles[id(m)] = len(spans)
                spans.append(_span(tokens, m["i"], m["j"], "MEAL", m["value"], text))
            elif m["kind"] == "diet":
                spans.append(_span(tokens, m["i"], m["j"], "DIET", m["value"], text))
            else:
                left, right = _clause(low, m["i"], m["j"])
                if any(t in NEGATION_CUES for t in left):
                    label = "EXCLUSION"
                elif any(_is_pantry_cue(t) for t in left + right):
                    label = "PANTRY"
                elif intent in ITEM_INTENTS:
                    label = "PRODUCT"
                else:
                    continue
                roles[id(m)] = len(spans)
                spans.append(_span(tokens, m["i"], m["j"], label, m["value"], text))

        dropped = set()
        for k, target in attachments:
            idx = roles.get(id(target))
            if idx is None or spans[idx]["label"] not in {"PRODUCT", "PANTRY"}:
                dropped.add(k)
            else:
                spans[k]["attach_to"] = idx
        kept = [k for k in range(len(spans)) if k not in dropped]
        order = sorted(kept, key=lambda k: spans[k]["start"])
        new_index = {old: new for new, old in enumerate(order)}
        result = []
        for old in order:
            span = dict(spans[old])
            if span["attach_to"] is not None:
                span["attach_to"] = new_index[span["attach_to"]]
            result.append(span)
        return result

    @staticmethod
    def _currency(tokens, low, owned, i: int, j: int) -> list[tuple[int, int]]:
        out = []
        if i >= 1 and not owned[i - 1] and low[i - 1] in CURRENCY_WORDS:
            out.append((i - 1, i))
        elif i >= 2 and low[i - 1] == "." and low[i - 2] == "rs" and tokens[i - 1][1] == tokens[i - 2][2] \
                and not owned[i - 2]:
            out.append((i - 2, i))
        if j < len(tokens) and not owned[j] and low[j] in CURRENCY_WORDS:
            end = j + 1
            if low[j] == "rs" and end < len(tokens) and low[end] == "." and tokens[end][1] == tokens[j][2]:
                end += 1
            out.append((j, end))
        return out


# ---------------------------------------------------------------- normalisation
def catalog_amount(quantity: Decimal, user_unit: str) -> tuple[str, str]:
    unit, factor = USER_UNIT_FACTORS[user_unit]
    return unit, format(quantize_amount(Decimal(quantity) * factor), "f")


def _amounts(spans: list[dict]) -> dict[int, tuple[Decimal | None, str | None]]:
    """Quantity and unit attached to each item span index."""
    out: dict[int, list] = {}
    for span in spans:
        if span["attach_to"] is None:
            continue
        entry = out.setdefault(span["attach_to"], [None, None])
        if span["label"] == "QUANTITY":
            entry[0] = Decimal(span["value"])
        elif span["label"] == "UNIT":
            entry[1] = span["value"]
    return {k: (v[0], v[1]) for k, v in out.items()}


def empty_request(request_id: str | None, intent: str) -> dict:
    return {"request_id": request_id, "intent": intent, "recipe_id": None, "servings": None, "items": [],
            "pantry": {}, "budget_minor": None, "currency": None if intent == "unsupported" else "PKR", "diet": [],
            "exclusions": [], "user_id": None, "needs_clarification": False, "clarification_type": None,
            "clarification_prompt": None}


class BaselineParser:
    """parse(text, session) -> StructuredRequest, using the trained intent model and rules."""

    def __init__(self, lexicon: Lexicon, intent_model, context_rules: bool = True, suggest_recipes: bool = False):
        self.lex = lexicon
        self.intent_model = intent_model
        self.context_rules = context_rules
        self.suggest_recipes = suggest_recipes
        self.slots = RuleSlotExtractor(lexicon)

    def extract_spans(self, text: str, intent: str) -> list[dict]:
        """Labelled spans with normalised values. E0 uses the rules; Phase 6 overrides this."""
        return self.slots.extract(text, intent)

    # ---- fields from spans
    def _fields(self, spans: list[dict], intent: str) -> dict:
        amounts = _amounts(spans)
        fields = {"recipe_id": None, "servings": None, "budget_minor": None, "diet": set(), "ambiguous_diet": False,
                  "exclusions": set(), "pantry": {}, "items": []}
        for idx, span in enumerate(spans):
            label, value = span["label"], span["value"]
            if value is None and label != "MEAL":
                continue  # a span whose text could not be normalised carries no field value
            if label == "MEAL" and intent == "plan_meal" and fields["recipe_id"] is None:
                fields["recipe_id"] = value
            elif label == "SERVINGS" and fields["servings"] is None:
                fields["servings"] = value
            elif label == "BUDGET" and fields["budget_minor"] is None:
                fields["budget_minor"] = int(Decimal(value) * 100)
            elif label == "DIET":
                if value == "ambiguous":
                    fields["ambiguous_diet"] = True
                else:
                    fields["diet"].add(value)
            elif label == "EXCLUSION":
                fields["exclusions"].add(value)
            elif label in {"PANTRY", "PRODUCT"}:
                quantity, user_unit = amounts.get(idx, (None, None))
                if quantity is None:
                    amount, unit = None, self.lex.first_unit(value)
                else:
                    unit, amount = catalog_amount(quantity, user_unit or "piece")
                if label == "PANTRY":
                    fields["pantry"].setdefault(value, amount)
                elif intent in ITEM_INTENTS:
                    fields["items"].append({"ingredient_id": value, "amount": amount, "unit": unit})
        return fields

    def _merge(self, request: dict, fields: dict, session: dict | None) -> dict:
        if request["intent"] == "revise_basket" and session:
            base = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
                    for k, v in session.items()}
            base.update(request_id=request["request_id"], intent="revise_basket")
            request = base
        else:
            request["recipe_id"] = fields["recipe_id"]
        if fields["servings"] is not None:
            request["servings"] = fields["servings"]
        if fields["budget_minor"] is not None:
            request["budget_minor"] = fields["budget_minor"]
        request["diet"] = sorted(set(request["diet"]) | fields["diet"])
        request["exclusions"] = sorted(set(request["exclusions"]) | fields["exclusions"])
        request["pantry"] = dict(sorted({**request["pantry"], **fields["pantry"]}.items()))
        request["items"] = list(request["items"]) + fields["items"]
        request["needs_clarification"] = False
        request["clarification_type"] = None
        request["clarification_prompt"] = None
        return request

    # ---- clarification
    def _pantry_unit(self, request: dict, ingredient_id: str) -> str:
        recipe = self.lex.recipes.get(request.get("recipe_id") or "")
        for line in (recipe or {}).get("ingredients", []):
            if line["ingredient_id"] == ingredient_id:
                return line["unit"]
        return self.lex.first_unit(ingredient_id)

    def _name(self, ingredient_id: str) -> str:
        return self.lex.ingredient_query(ingredient_id)

    def structural_issue(self, request: dict) -> tuple[str, str] | None:
        if request["intent"] == "plan_meal" and not request.get("recipe_id"):
            return "missing_recipe", self._recipe_prompt(request)
        for iid, amount in request["pantry"].items():
            if amount is None:
                return ("missing_pantry_quantity",
                        f"How much {self._name(iid)} do you already have (in {self._pantry_unit(request, iid)})?")
        for item in request["items"]:
            if item["amount"] is None:
                return "missing_item_quantity", f"How much {self._name(item['ingredient_id'])} do you need (in {item['unit']})?"
        return None

    def _recipe_prompt(self, request: dict) -> str:
        if not self.suggest_recipes:
            return "Which dish would you like?"
        names = [self.lex.recipe_name(rid) for rid in suggest_recipes(request, self.lex.catalog)]
        if not names:
            return "Which dish would you like?"
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
        return f"Which dish would you like? For example: {listed}."

    def _gate(self, request: dict, fields: dict, vague: bool) -> dict:
        if request["intent"] == "unsupported":
            return request
        issue = None
        if request["intent"] == "plan_meal" and not request.get("recipe_id"):
            issue = self.structural_issue(request)
        elif fields["ambiguous_diet"]:
            issue = ("ambiguous_diet", DIET_PROMPT)
        elif vague and fields["budget_minor"] is None:
            issue = ("missing_budget", "What is your budget in rupees?")
        else:
            issue = self.structural_issue(request)
        if issue:
            request.update(needs_clarification=True, clarification_type=issue[0], clarification_prompt=issue[1])
        return request

    # ---- public
    def predict_intent(self, text: str) -> tuple[str, dict]:
        scores = self.intent_model.decision_function([text])[0]
        classes = [str(c) for c in self.intent_model.classes_]
        return classes[int(scores.argmax())], {c: round(float(s), 6) for c, s in zip(classes, scores)}

    def apply_context_rules(self, text: str, intent: str, spans: list[dict], session: dict | None) -> str:
        """Dialogue-state rules on top of the classifier.

        - A revision needs a previous request: without a session, ``revise_basket`` becomes
          ``plan_meal`` if a meal is named, ``build_grocery_list`` if items are named, and
          ``plan_meal`` otherwise (which then asks for the dish).
        - With a session, a ``plan_meal`` or ``build_grocery_list`` message that names no meal
          is read as a revision of the current basket.
        """
        if not self.context_rules or intent == "unsupported":
            return intent
        has_meal = any(s["label"] == "MEAL" for s in spans)
        if intent == "revise_basket" and not session:
            if has_meal:
                return "plan_meal"
            listed = self.extract_spans(text, "build_grocery_list")
            return "build_grocery_list" if any(s["label"] == "PRODUCT" for s in listed) else "plan_meal"
        if intent in {"plan_meal", "build_grocery_list"} and session and not has_meal:
            return "revise_basket"
        return intent

    def parse_with_trace(self, text: str, session: dict | None = None, request_id: str | None = None) -> dict:
        classifier_intent, scores = self.predict_intent(text)
        spans = self.extract_spans(text, classifier_intent)
        intent = self.apply_context_rules(text, classifier_intent, spans, session)
        if intent != classifier_intent:
            spans = self.extract_spans(text, intent)
        request = empty_request(request_id, intent)
        if intent != "unsupported":
            tokens = [t.lower() for t, _, _ in tokenize(text)]
            vague = self.slots.vague_budget(tokens)
            fields = self._fields(spans, intent)
            request = self._gate(self._merge(request, fields, session), fields, vague)
        request = self.confidence_gate(request, scores, intent == classifier_intent)
        return {"request": request, "spans": spans, "classifier_intent": classifier_intent, "intent_scores": scores}

    def confidence_gate(self, request: dict, scores: dict, classifier_decided: bool) -> dict:
        """E0 has no confidence gating; the transformer parser overrides this."""
        return request

    def parse(self, text: str, session: dict | None = None, request_id: str | None = None) -> dict:
        return self.parse_with_trace(text, session, request_id)["request"]

    def answer(self, request: dict, answer: str) -> dict:
        """Apply the user's answer to the pending clarification; re-check what is still missing."""
        kind = request.get("clarification_type")
        out = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
               for k, v in request.items()}
        out["items"] = [dict(i) for i in request["items"]]
        spans = self.slots.extract(answer, "plan_meal")
        resolved = False
        if kind == "missing_recipe":
            meal = next((s["value"] for s in spans if s["label"] == "MEAL"), None)
            if meal:
                out["recipe_id"], resolved = meal, True
        elif kind == "missing_budget":
            budget = next((s["value"] for s in spans if s["label"] == "BUDGET"), None)
            if budget is not None:
                out["budget_minor"], resolved = int(Decimal(budget) * 100), True
        elif kind == "ambiguous_diet":
            diets = {s["value"] for s in spans if s["label"] == "DIET" and s["value"] != "ambiguous"}
            out["diet"], resolved = sorted(set(out["diet"]) | diets), True
        elif kind in {"missing_pantry_quantity", "missing_item_quantity"}:
            amount = self._answer_amount(answer)
            if amount is not None:
                quantity, user_unit = amount
                if kind == "missing_pantry_quantity":
                    iid = next(k for k, v in out["pantry"].items() if v is None)
                    target_unit = self._pantry_unit(out, iid)
                else:
                    entry = next(i for i in out["items"] if i["amount"] is None)
                    target_unit = entry["unit"]
                # A bare number is read in the line's own unit (g, ml and piece are also user units).
                unit, value = catalog_amount(quantity, user_unit or target_unit)
                if unit == target_unit:
                    if kind == "missing_pantry_quantity":
                        out["pantry"][iid] = value
                    else:
                        entry["amount"] = value
                    resolved = True
        if not resolved:
            return out
        out.update(needs_clarification=False, clarification_type=None, clarification_prompt=None)
        issue = self.structural_issue(out)
        if issue:
            out.update(needs_clarification=True, clarification_type=issue[0], clarification_prompt=issue[1])
        return out

    @staticmethod
    def _answer_amount(answer: str) -> tuple[Decimal, str | None] | None:
        tokens = tokenize(answer)
        for i in range(len(tokens)):
            parsed = parse_number(tokens, i)
            if parsed:
                value, j, _ = parsed
                unit = UNIT_WORDS.get(tokens[j][0].lower()) if j < len(tokens) else None
                return value, unit
        return None
