"""Phase 10: the interface logic (session), the six demo cases, and app.py driven headless
with Streamlit's AppTest (banner, request, clarification, recipe confirmation, edits,
"what changed", statuses and exports)."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.app import session as S  # noqa: E402

CONFIG = S.config()
DEMO = json.loads((ROOT / CONFIG["outputs"]["demo_cases"]).read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in CONFIG["demo_cases"]}
P = "baseline"  # fast and available everywhere; the demo record uses the app's configured parser
SUBMIT = "FormSubmitter:request_form-Plan my basket"
EDIT = "FormSubmitter:edit_form-Re-run with these changes"
REVISE = "FormSubmitter:revise_form-Update"


def first_text(case_id: str) -> str:
    return CASES[case_id]["steps"][0]["text"]


class SessionTests(unittest.TestCase):
    def test_banner_and_statuses(self):
        self.assertIn("SIMULATED", S.BANNER)
        solver = json.loads((ROOT / CONFIG["solver_config"]).read_text(encoding="utf-8"))
        for status in solver["statuses"]:
            self.assertIn(status, S.STATUS_VIEW)
        self.assertEqual(S.status_view({"status": "infeasible_in_scope"})[0], "Proven infeasible within scope")
        self.assertIn("not proof", S.status_view({"status": "solver_timeout"})[0])

    def test_parser_fallback(self):
        original = S.transformer_available
        try:
            S.transformer_available = lambda: False
            name, note = S.choose_parser("transformer")
            self.assertEqual(name, "baseline")
            self.assertIn("baseline", note)
        finally:
            S.transformer_available = original
        self.assertEqual(S.choose_parser("baseline"), ("baseline", None))

    def test_edit_run_and_changes(self):
        first = S.run(S.parse(first_text("D1_normal_feasible"), P))
        self.assertEqual(first["result"]["status"], "valid")
        target = first["result"]["lines"][0]["ingredient_id"]
        second = S.run(S.edit(first["request"], exclusions=[target]))
        changes = S.changes(first, second)
        self.assertTrue(any("Exclusions added" in c for c in changes))
        self.assertTrue(any(c.startswith("Line removed") for c in changes))
        self.assertNotIn(target, {line["ingredient_id"] for line in second["result"]["lines"]})
        broke = S.run(S.edit(first["request"], budget_minor=100))
        text = S.changes(first, broke)
        self.assertIn("Budget changed from PKR 2,500.00 to PKR 1.00.", text)
        self.assertFalse(any(c.startswith("Line removed") for c in text))  # no basket, not "removed" lines
        self.assertEqual(S.changes(first, first), ["Nothing changed."])

    def test_recipe_confirmation_for_a_broad_goal(self):
        request = S.parse(first_text("D3_dietary_exclusion"), P)
        self.assertEqual(request["clarification_type"], "missing_recipe")
        suggestions = S.recipe_suggestions(request)
        self.assertTrue(suggestions)
        confirmed = S.confirm_recipe(request, suggestions[0][0], P)
        self.assertFalse(confirmed["needs_clarification"])
        result = S.run(confirmed)["result"]
        self.assertEqual(result["status"], "valid")  # suggestions are feasible under the diet and budget
        self.assertLessEqual(result["total_cost_minor"], request["budget_minor"])

    def test_exports(self):
        record = S.run(S.parse(first_text("D1_normal_feasible"), P))
        csv_text = S.export_csv(record["result"])
        self.assertEqual(csv_text.count("\n") - 2, len(record["result"]["lines"]))
        self.assertIn("SIMULATED", csv_text)
        data = json.loads(S.export_json(record, [{"role": "user", "text": "hi"}]))
        self.assertEqual(data["result"]["status"], "valid")
        self.assertNotIn("timing", data["result"])
        self.assertTrue(data["result"]["validator"]["valid"])
        self.assertEqual(data["conversation"][0]["text"], "hi")
        failed = S.run(S.parse(first_text("D6_infeasible"), P))
        self.assertEqual(S.export_csv(failed["result"]).count("\n"), 2)  # header and status line only


class DemoCaseTests(unittest.TestCase):
    def test_all_six_demo_cases_work(self):
        self.assertEqual(len(DEMO["cases"]), 6)
        self.assertEqual(DEMO["cases_working"], 6)
        for case in DEMO["cases"]:
            self.assertTrue(case["works"], case["id"])
        kinds = {c["id"].split("_", 1)[1] for c in DEMO["cases"]}
        self.assertEqual(kinds, {"normal_feasible", "budget_revision", "dietary_exclusion", "pantry_quantity",
                                 "unfamiliar_wording", "infeasible"})

    def test_demo_texts_are_not_benchmark_texts(self):
        texts = {s["text"] for c in CONFIG["demo_cases"] for s in c["steps"] if "text" in s}
        annotations = (ROOT / "data" / "annotations" / "nlu.jsonl").read_text(encoding="utf-8")
        dev = (ROOT / "data" / "benchmarks" / "basket_dev.json").read_text(encoding="utf-8")
        for text in texts:
            self.assertNotIn(json.dumps(text)[1:-1], annotations)
            self.assertNotIn(json.dumps(text)[1:-1], dev)

    def test_demo_record_rebuilds_with_its_parser(self):
        if S.choose_parser()[0] != DEMO["parser"]:
            self.skipTest(f"the record was made with the {DEMO['parser']} parser, not available here")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_demo_cases.py"), "--check"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class AppUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from streamlit.testing.v1 import AppTest

        cls.AppTest = AppTest

    def app(self):
        at = self.AppTest.from_file(str(ROOT / "website" / "app.py"), default_timeout=600).run()
        self.assertFalse(at.exception)
        at.selectbox(key="parser").set_value(P).run()
        return at

    def submit(self, at, text):
        at.text_area(key="request_text").set_value(text)
        at.button(key=SUBMIT).click().run()
        self.assertFalse(at.exception)
        return at

    def test_banner_basket_edit_and_exports(self):
        at = self.app()
        self.assertIn("SIMULATED", at.warning[0].value)
        at.selectbox(key="user_id").set_value(S.history_users()[0]).run()
        self.submit(at, first_text("D1_normal_feasible"))
        self.assertTrue(at.success[0].value.startswith("**Valid basket.**"))
        self.assertEqual(len(at.dataframe), 1)
        fields = {row["Field"]: row["Value"] for row in at.table[0].value.to_dict("records")}
        self.assertEqual(fields["History user"], str(S.history_users()[0]))
        labels = [m.label for m in at.metric]
        self.assertIn("Budget remaining", labels)
        self.assertIn("Ingredient coverage", labels)
        self.assertEqual(len(at.get("download_button")), 2)
        at.number_input(key="edit_budget").set_value(1000.0)
        at.button(key=EDIT).click().run()
        self.assertTrue(at.error[0].value.startswith("**Proven infeasible within scope.**"))
        self.assertTrue(any("Budget changed" in m.value for m in at.markdown))
        at.button(key="use_suggestion").click().run()
        self.assertTrue(at.success[0].value.startswith("**Valid basket.**"))

    def test_clarification_answer(self):
        at = self.submit(self.app(), first_text("D4_pantry_quantity"))
        self.assertTrue(any("Clarification needed" in i.value for i in at.info))
        at.text_input(key="clarification_answer").set_value("I have 2 onions")
        at.button(key="send_answer").click().run()
        self.assertTrue(at.success[0].value.startswith("**Valid basket.**"))

    def test_recipe_confirmation_and_revision(self):
        at = self.submit(self.app(), first_text("D3_dietary_exclusion"))
        self.assertEqual(len(at.radio), 1)
        self.assertIn("Another dish...", at.radio[0].options)
        at.button(key="confirm_recipe").click().run()
        self.assertTrue(at.success[0].value.startswith("**Valid basket.**"))
        at.text_input(key="revise_text").set_value("Change to five servings")
        at.button(key=REVISE).click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Servings changed" in m.value for m in at.markdown))


if __name__ == "__main__":
    unittest.main()
