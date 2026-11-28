"""The interface's logic, kept out of Streamlit so it can be tested (Phase 10).

``app.py`` only draws widgets; every step it shows comes from these functions:

- ``parse`` / ``answer`` / ``revise``: the frozen parser (DistilBERT by default, the E0
  baseline when the checkpoints are missing);
- ``recipe_suggestions`` / ``confirm_recipe``: a broad meal goal ("something vegetarian")
  asks for a dish; the user confirms one of the feasible, cheapest-first suggestions;
- ``edit``: budget, exclusion, diet and servings edits made in the interface;
- ``run``: constrained selection (``configs/solver.json``) plus explanations from
  verified records;
- ``changes``: what changed between two runs, read from the two requests and results;
- ``export_csv`` / ``export_json``: the validated basket and its trace.
"""

from __future__ import annotations

import copy
import csv
import io
import json
from functools import lru_cache
from pathlib import Path

from smartcart.explanations import PRICE_NOTE, explain
from smartcart.explanations.basket import pkr

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "configs" / "app.json"
BANNER = ("Prices are SIMULATED in PKR for a research prototype. They are not real shop prices, and no "
          "savings claim is made.")
STATUS_VIEW = {
    "valid": ("Valid basket", "success"),
    "needs_clarification": ("Clarification needed", "info"),
    "solver_timeout": ("No solution found (the solver hit its time limit; this is not proof of infeasibility)",
                       "warning"),
    "no_basket_in_candidate_pool": ("No solution found among the retrieved candidates", "warning"),
    "infeasible_in_scope": ("Proven infeasible within scope", "error"),
    "unsupported": ("Request not supported", "warning"),
    "invalid_request": ("Request could not be resolved", "warning"),
    "invalid_solution": ("No valid basket (the validator rejected the solution)", "error"),
}
_UNSET = object()


@lru_cache(maxsize=1)
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads((ROOT / config()["catalog"]).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def solver_config() -> dict:
    return json.loads((ROOT / config()["solver_config"]).read_text(encoding="utf-8"))


def transformer_available() -> bool:
    nlu = json.loads((ROOT / "configs" / "nlu_transformer.json").read_text(encoding="utf-8"))
    seed = nlu["primary_seed"]
    return all((ROOT / nlu["checkpoints"].format(seed=seed, task=t) / "config.json").exists()
               for t in ("intent", "slots"))


def choose_parser(requested: str | None = None) -> tuple[str, str | None]:
    """(parser name, note): the configured parser, or the fallback with the reason."""
    name = requested or config()["parser"]
    if name == "transformer" and not transformer_available():
        return config()["fallback_parser"], "DistilBERT checkpoints not found: using the E0 baseline parser."
    return name, None


def get_parser(name: str):
    from smartcart.nlu.api import get_parser as load

    return load(catalog(), name)


def history_available() -> bool:
    from smartcart.associations import api

    return (ROOT / api._config()["data"]["baskets"]).is_file()


@lru_cache(maxsize=1)
def history_users() -> list[int]:
    """The first sampled Track B users (IDs only), for the optional history selector."""
    manifest = json.loads((ROOT / config()["trackb"]).read_text(encoding="utf-8"))
    return sorted(int(u) for u in manifest["users"])[:config()["history_users_listed"]]


# ----------------------------------------------------------------- requests
def parse(text: str, parser: str, user_id: int | None = None) -> dict:
    request = get_parser(parser).parse(text)
    request["user_id"] = user_id
    return request


def answer(request: dict, text: str, parser: str) -> dict:
    out = get_parser(parser).answer(request, text)
    out["user_id"] = request.get("user_id")
    return out


def revise(previous: dict, text: str, parser: str) -> dict:
    """A follow-up message, merged into the previous request by the parser's revision rules."""
    request = get_parser(parser).parse(text, session=previous)
    request["user_id"] = previous.get("user_id")
    return request


def recipe_suggestions(request: dict, limit: int | None = None) -> list[tuple[str, str]]:
    from smartcart.nlu.baseline_parser import suggest_recipes

    names = {r["id"]: r["name"] for r in catalog()["recipes"]}
    return [(rid, names[rid]) for rid in suggest_recipes(request, catalog(), limit or config()["recipe_suggestions"])]


def all_recipes() -> list[tuple[str, str]]:
    return sorted(((r["id"], r["name"]) for r in catalog()["recipes"]), key=lambda x: x[1])


def confirm_recipe(request: dict, recipe_id: str, parser: str) -> dict:
    out = copy.deepcopy(request)
    out.update(intent="plan_meal", recipe_id=recipe_id, needs_clarification=False, clarification_type=None,
               clarification_prompt=None)
    issue = get_parser(parser).structural_issue(out)
    if issue:
        out.update(needs_clarification=True, clarification_type=issue[0], clarification_prompt=issue[1])
    return out


def edit(request: dict, budget_minor=_UNSET, exclusions=_UNSET, diet=_UNSET, servings=_UNSET) -> dict:
    out = copy.deepcopy(request)
    if budget_minor is not _UNSET:
        out["budget_minor"] = budget_minor
    if exclusions is not _UNSET:
        out["exclusions"] = sorted(set(exclusions))
    if diet is not _UNSET:
        out["diet"] = sorted(set(diet))
    if servings is not _UNSET:
        out["servings"] = servings
    return out


def run(request: dict) -> dict:
    from smartcart.optimization.cpsat import select_basket

    result = select_basket(request, catalog(), solver_config())
    return {"request": request, "result": result, "explanation": explain(result, request, catalog())}


# ----------------------------------------------------------------- views
def status_view(result: dict) -> tuple[str, str]:
    return STATUS_VIEW.get(result["status"], (result["status"], "warning"))


def basket_rows(result: dict) -> list[dict]:
    products = {p["id"]: p for p in catalog()["products"]}
    ingredients = {i["id"]: i["name"] for i in catalog()["ingredients"]}
    rows = []
    for line in result.get("lines", []):
        p = products[line["product_id"]]
        rows.append({"Ingredient": ingredients[line["ingredient_id"]],
                     "Product": p["name"].replace("SIMULATED ", "", 1),
                     "Packs": line["pack_count"], "Pack size": f"{p['pack_amount']} {line['unit']}",
                     "Need": f"{line['need']} {line['unit']}", "Bought": f"{line['bought']} {line['unit']}",
                     "Left over": f"{line['surplus']} {line['unit']}",
                     "Line cost (PKR, simulated)": f"{line['line_cost_minor'] / 100:,.2f}",
                     "Cheapest eligible": "yes" if line["cheapest_option"] else "no"})
    return rows


def coverage(result: dict) -> dict:
    validator = result.get("validator") or {}
    return {"coverage": validator.get("coverage"),
            "lines_bought": len(result.get("lines", [])),
            "covered_by_pantry": [c["ingredient_id"] for c in result.get("covered_by_pantry", [])],
            "excluded": [e["ingredient_id"] for e in result.get("excluded_lines", [])]}


def request_fields(request: dict) -> dict:
    recipes = {r["id"]: r["name"] for r in catalog()["recipes"]}
    ingredients = {i["id"]: i["name"] for i in catalog()["ingredients"]}
    return {"Intent": request.get("intent"),
            "Recipe": recipes.get(request.get("recipe_id"), request.get("recipe_id")),
            "Servings": request.get("servings"),
            "Items": ", ".join(f"{i['amount']} {i['unit']} {ingredients.get(i['ingredient_id'], i['ingredient_id'])}"
                               for i in request.get("items", [])) or None,
            "Pantry": ", ".join(f"{ingredients.get(k, k)}: {v}" for k, v in request.get("pantry", {}).items()) or None,
            "Budget": pkr(request["budget_minor"]) if request.get("budget_minor") is not None else None,
            "Diet": ", ".join(request.get("diet") or []) or None,
            "Exclusions": ", ".join(ingredients.get(e, e) for e in request.get("exclusions") or []) or None,
            "History user": request.get("user_id")}


def changes(before: dict, after: dict) -> list[str]:
    """What changed between two runs ({"request", "result"}), from the records only."""
    ingredients = {i["id"]: i["name"] for i in catalog()["ingredients"]}
    products = {p["id"]: p["name"].replace("SIMULATED ", "", 1) for p in catalog()["products"]}
    rb, ra = before["request"], after["request"]
    out = []
    if rb.get("budget_minor") != ra.get("budget_minor"):
        out.append(f"Budget changed from {pkr(rb.get('budget_minor'))} to {pkr(ra.get('budget_minor'))}.")
    if rb.get("servings") != ra.get("servings"):
        out.append(f"Servings changed from {rb.get('servings')} to {ra.get('servings')}.")
    if rb.get("recipe_id") != ra.get("recipe_id"):
        out.append(f"Dish changed to {ra.get('recipe_id')}.")
    for field, word in (("diet", "Diet"), ("exclusions", "Exclusions")):
        added = set(ra.get(field) or []) - set(rb.get(field) or [])
        dropped = set(rb.get(field) or []) - set(ra.get(field) or [])
        if added:
            out.append(f"{word} added: {', '.join(ingredients.get(x, x) for x in sorted(added))}.")
        if dropped:
            out.append(f"{word} removed: {', '.join(ingredients.get(x, x) for x in sorted(dropped))}.")
    if rb.get("pantry") != ra.get("pantry"):
        out.append("Pantry changed: " + ", ".join(f"{ingredients.get(k, k)} {v}" for k, v in
                                                  (ra.get("pantry") or {}).items()) + ".")
    sb, sa = before["result"]["status"], after["result"]["status"]
    if sb != sa:
        out.append(f"Status changed from {status_view(before['result'])[0]} to {status_view(after['result'])[0]}.")
    if sb == "valid" and sa != "valid":
        out.append("There is no basket under the new request; the previous basket no longer applies.")
    if sb != "valid" or sa != "valid":
        return out or ["Nothing changed."]
    lb = {line["ingredient_id"]: line for line in before["result"].get("lines", [])}
    la = {line["ingredient_id"]: line for line in after["result"].get("lines", [])}
    for iid in sorted(set(lb) - set(la)):
        out.append(f"Line removed: {ingredients[iid]} ({products[lb[iid]['product_id']]}).")
    for iid in sorted(set(la) - set(lb)):
        out.append(f"Line added: {ingredients[iid]} ({products[la[iid]['product_id']]}).")
    for iid in sorted(set(la) & set(lb)):
        a, b = lb[iid], la[iid]
        if (a["product_id"], a["pack_count"]) != (b["product_id"], b["pack_count"]):
            out.append(f"{ingredients[iid]}: {a['pack_count']} x {products[a['product_id']]} -> "
                       f"{b['pack_count']} x {products[b['product_id']]}.")
    tb, ta = before["result"].get("total_cost_minor"), after["result"].get("total_cost_minor")
    if tb != ta:
        out.append(f"Total changed from {pkr(tb)} to {pkr(ta)}.")
    return out or ["Nothing changed."]


# ----------------------------------------------------------------- exports
def export_csv(result: dict) -> str:
    buffer = io.StringIO()
    rows = basket_rows(result) if result["status"] == "valid" else []
    fields = list(rows[0]) if rows else ["Ingredient", "Product", "Packs"]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    buffer.write(f"# status: {result['status']}; total: {pkr(result.get('total_cost_minor'))}; {PRICE_NOTE}\n")
    return buffer.getvalue()


def export_json(run_record: dict, history: list[dict] | None = None) -> str:
    result = {k: v for k, v in run_record["result"].items() if k != "timing"}
    return json.dumps({"price_note": PRICE_NOTE, "request": run_record["request"], "result": result,
                       "explanation": run_record["explanation"], "conversation": history or []},
                      indent=2, ensure_ascii=False, default=str) + "\n"
