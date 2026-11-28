"""Phase 11: run configurations, the lock check, unified scoring, the family bootstrap,
agreement with the committed dev results, and the integrity of the test-split outputs."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.pipeline.experiment import (  # noqa: E402
    family_bootstrap, run_scenario, run_settings, score, summarize, row, verify_lock,
)

EVAL = json.loads((ROOT / "configs" / "experiments" / "evaluation.json").read_text(encoding="utf-8"))
SOLVER = json.loads((ROOT / "configs" / "solver.json").read_text(encoding="utf-8"))
RETRIEVAL = json.loads((ROOT / "configs" / "retrieval.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / EVAL["data"]["catalog"]).read_text(encoding="utf-8"))
DEV = json.loads((ROOT / EVAL["data"]["basket"]["dev"]).read_text(encoding="utf-8"))["scenarios"]
SUMMARY_PATH = ROOT / EVAL["outputs"]["summary"]
HAS_BASKETS = (ROOT / "data" / "interim" / "instacart" / "sample_order_products.csv.gz").is_file()


def settings(run):
    return run_settings(json.loads((ROOT / "configs" / "experiments" / f"{run}.json").read_text(encoding="utf-8")),
                        SOLVER)


class ConfigTests(unittest.TestCase):
    def test_every_planned_run_has_a_frozen_config(self):
        self.assertEqual(EVAL["runs"], ["E0", "E1", "E2", "E3", "E4", "A1", "A2", "A3", "A4"])
        for run in EVAL["runs"]:
            cfg = json.loads((ROOT / "configs" / "experiments" / f"{run}.json").read_text(encoding="utf-8"))
            self.assertTrue(cfg["frozen"])
            self.assertEqual(cfg["max_clarification_turns"], 3)

    def test_runs_differ_exactly_as_planned(self):
        s = {run: settings(run) for run in EVAL["runs"]}
        self.assertEqual((s["E0"]["parser"], s["E0"]["retrieval"], s["E0"]["selection"]),
                         ("baseline", {"method": "tfidf", "product_text": "legacy", "top_k": 10},
                          "independent_cheapest"))
        self.assertEqual(s["E1"]["parser"], "transformer")
        self.assertEqual(s["E1"]["retrieval"], s["E0"]["retrieval"])
        phase7 = {"method": "minilm", "product_text": RETRIEVAL["product_text"]["selected"],
                  "top_k": RETRIEVAL["candidate_count"]["selected"]}
        self.assertEqual(s["E2"]["retrieval"], phase7)
        self.assertEqual((s["E3"]["selection"], s["E3"]["weights"]["history"], s["E3"]["weights"]["pair"]),
                         ("constrained", 0.0, 0.0))
        self.assertEqual({k: s["E4"]["weights"][k] for k in ("history", "pair")},
                         {k: SOLVER["objective"]["fixed_weights"][k] for k in ("history", "pair")})
        self.assertEqual(s["A1"]["parser"], "baseline")
        self.assertEqual({**s["A1"], "run": "E4", "parser": "transformer"}, s["E4"])
        self.assertEqual(s["A2"]["retrieval"], {**phase7, "method": "tfidf"})
        self.assertEqual((s["A3"]["weights"]["history"], s["A3"]["weights"]["pair"]), (0.1, 0.0))
        self.assertEqual({**s["A4"], "run": "E2"}, s["E2"])  # coincides by construction (documented)
        self.assertEqual(s["E4"]["solver"]["candidates"]["top_k"], 40)

    def test_lock_check(self):
        self.assertTrue(all(verify_lock(ROOT, ROOT / EVAL["lock"]).values()))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lock = (ROOT / EVAL["lock"]).read_text(encoding="utf-8")
            (tmp / "lock.md").write_text(lock, encoding="utf-8")
            for path in verify_lock(ROOT, ROOT / EVAL["lock"]):
                (tmp / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / path, tmp / path)
            target = tmp / "data" / "benchmarks" / "basket_test.json"
            target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
            result = verify_lock(tmp, tmp / "lock.md")
            self.assertFalse(result["data/benchmarks/basket_test.json"])
            self.assertTrue(result["data/benchmarks/retrieval_test.json"])

    def test_development_switches_refuse_the_test_split(self):
        for flag in (["--seeds", "13"], ["--dev-parser", "baseline"]):
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate.py"), "--config",
                                     "configs/experiments/E1.json", *flag], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dev only", result.stderr + result.stdout)


class ScoringTests(unittest.TestCase):
    def scenario(self, label):
        return next(s for s in DEV if s["label"] == label)

    def fake(self, status):
        return {"request": {}, "clarifications_asked": [], "turns": 0, "status": status,
                "basket": {"status": status, "purchased": []}}

    def test_infeasibility_statuses_per_selector(self):
        s = self.scenario("infeasible")
        self.assertTrue(score(self.fake("over_budget"), s, CATALOG, "independent_cheapest")["success"])
        self.assertTrue(score(self.fake("infeasible_in_scope"), s, CATALOG, "constrained")["success"])
        self.assertFalse(score(self.fake("solver_timeout"), s, CATALOG, "constrained")["success"])
        self.assertFalse(score(self.fake("infeasible_in_scope"), s, CATALOG, "independent_cheapest")["success"])

    def test_false_rejection_and_unnecessary_question(self):
        s = self.scenario("feasible")
        scored = score(self.fake("infeasible_in_scope"), s, CATALOG, "constrained")
        self.assertTrue(scored["false_rejection"])
        self.assertFalse(scored["success"])
        asked = {**self.fake("needs_clarification"), "clarifications_asked": ["missing_budget"]}
        self.assertTrue(score(asked, s, CATALOG, "constrained")["unnecessary_clarification"])

    def test_harness_reproduces_committed_dev_results(self):
        if not HAS_BASKETS:
            self.skipTest("history scores need data/interim/instacart")
        committed = json.loads((ROOT / "results" / "metrics" / "E0_basket_dev.json").read_text(encoding="utf-8"))
        for run, expected in (("E0", sum(v["success"] for v in committed["gold_input"]["by_label"].values())),
                              ("E4", json.loads((ROOT / "results" / "metrics" / "solver_dev.json")
                                                .read_text(encoding="utf-8"))["results"]["success"])):
            cfg = settings(run)
            rows = []
            for s in DEV:
                result = run_scenario(s, CATALOG, cfg, mode="gold_input")
                rows.append(row(s, result, score(result, s, CATALOG, cfg["selection"]), CATALOG, cfg,
                                "gold_input", None))
            self.assertEqual(summarize(rows)["success"], expected, run)


class BootstrapTests(unittest.TestCase):
    def test_family_bootstrap(self):
        families = {f"s{i}": f"f{i // 2}" for i in range(10)}
        same = {s: 1.0 for s in families}
        self.assertEqual(family_bootstrap(same, same, families, 200, 1)["ci95"], [0.0, 0.0])
        a = {s: 1.0 for s in families}
        b = {s: (0.0 if i < 5 else 1.0) for i, s in enumerate(families)}
        out = family_bootstrap(a, b, families, 500, 1)
        self.assertAlmostEqual(out["difference"], 0.5)
        self.assertLessEqual(out["ci95"][0], 0.5)
        self.assertGreaterEqual(out["ci95"][1], 0.5)
        self.assertEqual(out, family_bootstrap(a, b, families, 500, 1))
        self.assertEqual(out["families"], 5)


@unittest.skipUnless(SUMMARY_PATH.is_file(), "the Phase 11 test outputs are not generated yet")
class TestOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    def rows(self, run, mode, seed=""):
        path = ROOT / EVAL["outputs"]["rows"].format(run=run, mode=mode, seed=seed)
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]

    def test_every_run_and_mode_has_rows_and_metrics(self):
        self.assertEqual(self.summary["split"], "test")
        for run in EVAL["runs"]:
            metrics = json.loads((ROOT / EVAL["outputs"]["run_metrics"].format(run=run)).read_text(encoding="utf-8"))
            self.assertEqual(metrics["split"], "test")
            self.assertEqual(len(self.rows(run, "gold_input")), 200)
            seeds = metrics["end_to_end"]["seeds"]
            if settings(run)["parser"] == "transformer":
                self.assertEqual(seeds, EVAL["seeds"])
            for seed in seeds or [None]:
                rows = self.rows(run, "end_to_end", "" if seed is None else f"_seed{seed}")
                self.assertEqual(len(rows), 200)
                self.assertEqual(summarize(rows), metrics["end_to_end"]["per_seed"]["single" if seed is None
                                                                                    else str(seed)])
            self.assertEqual(summarize(self.rows(run, "gold_input")), metrics["gold_input"])

    def test_test_split_composition(self):
        rows = self.rows("E0", "gold_input")
        labels = [r["label"] for r in rows]
        self.assertEqual((labels.count("feasible"), labels.count("infeasible"), labels.count("clarification")),
                         (120, 40, 40))

    def test_report_rebuilds(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_report.py"), "--check"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_comparisons_are_present(self):
        self.assertEqual(set(self.summary["comparisons"]), {f"{a} - {b}" for a, b in EVAL["comparisons"]})


if __name__ == "__main__":
    unittest.main()
