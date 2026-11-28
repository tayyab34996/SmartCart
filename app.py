"""SmartCart: an offline grocery-basket assistant (Phase 10, D8).

Run with:  .\\.venv\\Scripts\\python -m streamlit run app.py

Every value shown comes from the frozen pipeline: the parser, constrained selection
(``configs/solver.json``), the independent validator and explanations built from verified
records. The logic lives in ``src/smartcart/app/session.py``; this file only draws it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import streamlit as st  # noqa: E402

from smartcart.app import session as S  # noqa: E402

st.set_page_config(page_title="SmartCart", layout="wide")
state = st.session_state
for key, default in (("request", None), ("run", None), ("changes", None), ("conversation", [])):
    state.setdefault(key, default)


@st.cache_resource(show_spinner="Loading the parser and retrieval models...")
def warm_up(parser: str) -> bool:
    """Load the parser and the MiniLM index once per process (cold-load cost)."""
    S.get_parser(parser)
    from smartcart.retrieval.api import retrieve_candidates

    cfg = S.solver_config()["candidates"]
    retrieve_candidates("egg", S.catalog(), method=cfg["method"], top_k=1, product_text=cfg["product_text"])
    return True


def log(role: str, text: str) -> None:
    state.conversation.append({"role": role, "text": text})


def solve(request: dict, previous: dict | None = None) -> None:
    state.request = request
    record = S.run(request)
    state.changes = S.changes(previous, record) if previous else None
    state.run = record
    log("assistant", record["explanation"]["summary"])


def reset() -> None:
    for key in ("request", "run", "changes"):
        state[key] = None
    state.conversation = []


# ------------------------------------------------------------------ sidebar
st.warning(S.BANNER, icon="⚠️")
st.title("SmartCart")
st.caption("Plan a meal or a grocery list within a budget. Offline research prototype.")

with st.sidebar:
    st.header("Settings")
    default_parser, note = S.choose_parser()
    options = ["transformer", "baseline"] if S.transformer_available() else ["baseline"]
    parser = st.selectbox("Parser", options, index=options.index(default_parser), key="parser",
                          help="transformer = fine-tuned DistilBERT (Phase 6); baseline = E0 rules + TF-IDF/SVC")
    if note:
        st.info(note)
    users = [None] + S.history_users()
    user_id = st.selectbox("Shopper with purchase history (optional)", users, key="user_id",
                           format_func=lambda u: "None" if u is None else f"Instacart sample user {u}")
    if user_id is not None and not S.history_available():
        st.info("History needs data/interim/instacart/ (run scripts/prepare_transactions.py); scores will be 0.")
    st.button("Start over", on_click=reset, key="reset")
    st.caption("Statuses: valid basket, clarification needed, no solution found, proven infeasible within scope.")

warm_up(parser)

# ------------------------------------------------------------------ request
with st.form("request_form"):
    text = st.text_area("What would you like to cook or buy?", key="request_text",
                        placeholder="e.g. Chicken curry in a hurry for 4 people, budget 2500 rupees")
    submitted = st.form_submit_button("Plan my basket")
if submitted and text.strip():
    reset()
    log("user", text.strip())
    request = S.parse(text.strip(), parser, user_id)
    state.request = request
    if request["needs_clarification"]:
        log("assistant", request["clarification_prompt"] or request["clarification_type"])
    else:
        solve(request)

request = state.request
if request is not None:
    with st.expander("What I understood", expanded=True):
        fields = {k: v for k, v in S.request_fields(request).items() if v not in (None, "")}
        st.table([{"Field": k, "Value": str(v)} for k, v in fields.items()])

    # -------------------------------------------------------------- clarification
    if request["needs_clarification"]:
        st.info(f"**Clarification needed:** {request['clarification_prompt'] or request['clarification_type']}")
        if request["clarification_type"] == "missing_recipe":
            suggestions = S.recipe_suggestions(request)
            labels = [name for _, name in suggestions] + ["Another dish..."]
            pick = st.radio("Suggested dishes (feasible under your diet and budget, cheapest first)", labels,
                            key="recipe_pick")
            ids = dict((name, rid) for rid, name in suggestions)
            if pick == "Another dish...":
                recipes = S.all_recipes()
                other = st.selectbox("Choose a dish", recipes, format_func=lambda r: r[1], key="recipe_other")
                chosen = other[0]
            else:
                chosen = ids[pick]
            if st.button("Use this dish", key="confirm_recipe"):
                log("user", f"(confirmed dish {chosen})")
                confirmed = S.confirm_recipe(request, chosen, parser)
                state.request = confirmed
                if confirmed["needs_clarification"]:
                    log("assistant", confirmed["clarification_prompt"])
                else:
                    solve(confirmed)
                st.rerun()
        else:
            reply = st.text_input("Your answer", key="clarification_answer")
            if st.button("Answer", key="send_answer") and reply.strip():
                log("user", reply.strip())
                updated = S.answer(request, reply.strip(), parser)
                state.request = updated
                if updated["needs_clarification"]:
                    log("assistant", updated["clarification_prompt"] or "I still need that detail.")
                else:
                    solve(updated)
                st.rerun()

# ------------------------------------------------------------------ result
record = state.run
if record is not None and not record["request"]["needs_clarification"]:
    result, explanation = record["result"], record["explanation"]
    label, kind = S.status_view(result)
    getattr(st, kind)(f"**{label}.** {explanation['summary']}")
    if state.changes:
        st.subheader("What changed")
        for line in state.changes:
            st.markdown(f"- {line}")

    if result["status"] == "valid":
        cov = S.coverage(result)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total (simulated PKR)", f"{result['total_cost_minor'] / 100:,.2f}")
        remaining = result["budget_remaining_minor"]
        c2.metric("Budget remaining", "no budget" if remaining is None else f"{remaining / 100:,.2f}")
        c3.metric("Ingredient coverage", f"{(cov['coverage'] or 0) * 100:.0f}%")
        c4.metric("Products", cov["lines_bought"])
        if result["lines"]:
            st.dataframe(S.basket_rows(result), hide_index=True, width="stretch")
        st.subheader("Why these products")
        for line in explanation["lines"]:
            st.markdown(f"- {line}")
    for note_text in explanation["notes"]:
        st.caption(note_text)

    if result["status"] == "infeasible_in_scope" and result.get("suggested_budget_minor"):
        if st.button(f"Use the suggested budget ({result['suggested_budget_minor'] / 100:,.2f} PKR)",
                     key="use_suggestion"):
            log("user", "(raised the budget to the suggestion)")
            solve(S.edit(record["request"], budget_minor=result["suggested_budget_minor"]), previous=record)
            st.rerun()

    # -------------------------------------------------------------- edits
    st.subheader("Change the request")
    req = record["request"]
    with st.form("edit_form"):
        has_budget = st.checkbox("Use a budget", value=req.get("budget_minor") is not None, key="edit_has_budget")
        budget = st.number_input("Budget (PKR)", min_value=0.0, step=50.0, key="edit_budget",
                                 value=float((req.get("budget_minor") or 0) / 100))
        resolved_lines = [line["ingredient_id"] for line in result.get("lines", [])]
        exclusion_options = sorted(set(resolved_lines) | set(req.get("exclusions") or []))
        names = {i["id"]: i["name"] for i in S.catalog()["ingredients"]}
        exclusions = st.multiselect("Leave out these ingredients", exclusion_options,
                                    default=req.get("exclusions") or [], format_func=lambda i: names.get(i, i),
                                    key="edit_exclusions")
        diets = ["vegetarian", "vegan", "gluten_free", "dairy_free", "nut_free"]
        diet = st.multiselect("Dietary rules", diets, default=req.get("diet") or [], key="edit_diet",
                              format_func=lambda d: d.replace("_", "-"))
        rerun = st.form_submit_button("Re-run with these changes")
    if rerun:
        edited = S.edit(req, budget_minor=round(budget * 100) if has_budget else None,
                        exclusions=exclusions, diet=diet)
        log("user", "(edited the request)")
        solve(edited, previous=record)
        st.rerun()

    with st.form("revise_form"):
        follow_up = st.text_input("Or say what to change", key="revise_text",
                                  placeholder="e.g. make it 5 servings, or can we do it for 1500 rupees instead")
        revised = st.form_submit_button("Update")
    if revised and follow_up.strip():
        log("user", follow_up.strip())
        updated = S.revise(req, follow_up.strip(), parser)
        if updated["needs_clarification"]:
            state.request = updated
            log("assistant", updated["clarification_prompt"] or updated["clarification_type"])
        else:
            solve(updated, previous=record)
        st.rerun()

    # -------------------------------------------------------------- exports
    st.subheader("Export")
    e1, e2 = st.columns(2)
    e1.download_button("Basket (CSV)", S.export_csv(result), file_name="smartcart_basket.csv", mime="text/csv",
                       key="export_csv")
    e2.download_button("Basket and trace (JSON)", S.export_json(record, state.conversation),
                       file_name="smartcart_basket.json", mime="application/json", key="export_json")

if state.conversation:
    with st.expander("Conversation"):
        for turn in state.conversation:
            st.markdown(f"**{turn['role']}:** {turn['text']}")
