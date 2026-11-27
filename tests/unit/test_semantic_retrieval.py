"""Phase 7: product text, MiniLM + FAISS retrieval, the diet-filter fix, the dev-only
benchmark, the frozen selection and the rebuild checks."""

import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import smartcart.retrieval.benchmark as benchmark  # noqa: E402
from smartcart.retrieval import api  # noqa: E402
from smartcart.retrieval.api import retrieve_candidates, search_products  # noqa: E402
from smartcart.retrieval.filtering import filter_eligible_candidates  # noqa: E402
from smartcart.retrieval.index import MODEL_REVISION, MiniLMIndex, TfidfIndex, rank  # noqa: E402
from smartcart.retrieval.product_text import (  # noqa: E402
    SELECTABLE_VARIANTS, catalog_texts, display_name, product_text,
)
from smartcart.retrieval.tfidf import _format_product_text  # noqa: E402

CONFIG = json.loads((ROOT / "configs" / "retrieval.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / CONFIG["data"]["catalog"]).read_text(encoding="utf-8"))
PRODUCTS = {p["id"]: p for p in CATALOG["products"]}
DEV = json.loads((ROOT / CONFIG["data"]["retrieval_dev"]).read_text(encoding="utf-8"))["queries"]
METRICS = json.loads((ROOT / CONFIG["outputs"]["metrics"]).read_text(encoding="utf-8"))


def run_script(name, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / name), *args], cwd=ROOT,
                          capture_output=True, text=True)


class DietFilterTests(unittest.TestCase):
    def test_only_allowed_satisfies_a_diet(self):
        cands = [{"id": v, "dietary": {"vegetarian": v}} for v in ("allowed", "unknown", "disallowed")]
        cands.append({"id": "bool", "dietary": {"vegetarian": True}})  # not a catalog value
        kept = filter_eligible_candidates(cands, dietary_rules=["vegetarian"])
        self.assertEqual([c["id"] for c in kept], ["allowed"])

    def test_catalog_dietary_variants_now_pass(self):
        allowed = [p for p in CATALOG["products"] if p["dietary"].get("vegetarian") == "allowed"]
        self.assertTrue(allowed)
        self.assertEqual(len(filter_eligible_candidates(allowed, dietary_rules=["vegetarian"])),
                         len([p for p in allowed if p["available"]]))


class ProductTextTests(unittest.TestCase):
    def test_display_name_drops_marker_brand_and_pack(self):
        self.assertEqual(display_name({"name": "SIMULATED SmartCart Basics Parmesan cheese (grated) 400 g"}),
                         "parmesan cheese grated")
        self.assertEqual(display_name({"name": "SIMULATED Egg 12 piece"}), "egg")
        self.assertEqual(display_name({"name": "SIMULATED SmartCart Select White mushroom 24 pieces"}),
                         "white mushroom")
        for text in catalog_texts(CATALOG, "display_name"):
            self.assertNotIn("simulated", text)
            self.assertNotIn("smartcart", text)

    def test_legacy_text_is_the_phase_1_tfidf_text(self):
        for p in CATALOG["products"]:
            self.assertEqual(product_text(p, "legacy"), _format_product_text(p))

    def test_alias_text_is_diagnostic_only(self):
        self.assertNotIn("display_name_aliases", SELECTABLE_VARIANTS)
        self.assertEqual(CONFIG["product_text"]["candidates"], list(SELECTABLE_VARIANTS))
        self.assertIn("display_name_aliases", CONFIG["product_text"]["diagnostic_only"])


class RetrievalApiTests(unittest.TestCase):
    def test_default_product_text_is_the_frozen_choice(self):
        self.assertEqual(api.DEFAULT_PRODUCT_TEXT, CONFIG["product_text"]["selected"])
        self.assertEqual(MODEL_REVISION, CONFIG["model"]["revision"])

    def test_minilm_contract(self):
        ranked = retrieve_candidates("cheddar", CATALOG, method="minilm", top_k=10)
        self.assertEqual([r["rank"] for r in ranked], list(range(1, 11)))
        self.assertTrue(all(0.0 <= r["retrieval_score"] <= 1.0 for r in ranked))
        scores = [r["retrieval_score"] for r in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(ranked, retrieve_candidates("cheddar", CATALOG, method="minilm", top_k=10))
        self.assertEqual(PRODUCTS[ranked[0]["product_id"]]["ingredient_id"], "cheddar")

    def test_both_methods_rank_the_whole_catalog_without_hard_rules(self):
        for method in ("tfidf", "minilm"):
            everything = search_products("cheddar cheese", CATALOG, method=method, top_k=None)
            self.assertEqual(sorted(r["product_id"] for r in everything), sorted(PRODUCTS))
            top = retrieve_candidates("cheddar", CATALOG, method=method, top_k=20)
            self.assertTrue(any(PRODUCTS[r["product_id"]]["ingredient_id"] != "cheddar" for r in top))

    def test_ties_go_to_the_product_id(self):
        ranked = rank([0.5, 0.9, 0.5, 0.5000000001], ["c", "a", "b", "d"])
        self.assertEqual([i for i, _ in ranked], [1, 2, 0, 3])  # a, then b, c, d tied at 6 decimals

    def test_minilm_understands_what_tfidf_cannot(self):
        tfidf = search_products("courgette", CATALOG, method="tfidf", top_k=1)[0]
        minilm = search_products("courgette", CATALOG, method="minilm", top_k=1)[0]
        self.assertEqual(tfidf["retrieval_score"], 0.0)
        self.assertEqual(PRODUCTS[minilm["product_id"]]["ingredient_id"], "zucchini")

    def test_tfidf_index_matches_the_phase_1_retriever(self):
        from smartcart.retrieval.tfidf import build_tfidf_retriever, search_products_tfidf

        ids = [p["id"] for p in CATALOG["products"]]
        new = TfidfIndex(ids, catalog_texts(CATALOG, "legacy"))
        state = build_tfidf_retriever(CATALOG["products"])
        for query in ("cheddar cheese", "egg", "olive oil"):
            old = search_products_tfidf(query, state, top_k=10)
            got = rank(new.scores(query), ids, 10, round_before_sort=False)
            self.assertEqual([ids[i] for i, _ in got], [p["id"] for p in old])


class IndexCacheTests(unittest.TestCase):
    def test_cache_is_used_only_when_the_input_hash_matches(self):
        ids = [p["id"] for p in CATALOG["products"]][:30]
        texts = catalog_texts(CATALOG, CONFIG["product_text"]["selected"])[:30]
        built = MiniLMIndex(ids, texts)
        with tempfile.TemporaryDirectory() as tmp:
            built.save(Path(tmp), "probe")
            loaded = MiniLMIndex.load_cached(Path(tmp), "probe", ids, texts, encoder=built.encoder)
            self.assertIsNotNone(loaded)
            self.assertEqual(list(loaded.scores("egg")), list(built.scores("egg")))
            changed = texts[:-1] + [texts[-1] + " changed"]
            self.assertIsNone(MiniLMIndex.load_cached(Path(tmp), "probe", ids, changed, encoder=built.encoder))
            self.assertIsNone(MiniLMIndex.load_cached(Path(tmp), "missing", ids, texts, encoder=built.encoder))


class BenchmarkTests(unittest.TestCase):
    def test_gold_ingredient_never_reaches_the_filter(self):
        seen = []
        original = benchmark.filter_eligible_candidates

        def recording(cands, **kwargs):
            seen.append(kwargs)
            return original(cands, **kwargs)

        benchmark.filter_eligible_candidates = recording
        try:
            benchmark.evaluate(DEV[:3], CATALOG, "tfidf", "display_name", [5, 10])
        finally:
            benchmark.filter_eligible_candidates = original
        self.assertEqual(len(seen), 3)
        for kwargs in seen:
            self.assertNotIn("required_ingredient", kwargs)

    def test_wrong_ingredient_first_is_penalised(self):
        m = benchmark.query_metrics(["flour1", "egg1", "egg2"], {"egg1", "egg2"}, [5, 10])
        self.assertEqual(m["reciprocal_rank"], 0.5)
        self.assertEqual(m["recall"][5], 1.0)
        miss = benchmark.query_metrics([f"x{i}" for i in range(10)] + ["egg1"], {"egg1"}, [5, 10])
        self.assertEqual((miss["reciprocal_rank"], miss["recall"][10], miss["first_relevant_rank"]), (0.0, 0.0, 11))

    def test_selection_rules(self):
        results = {v: {m: {"summary": {"recall_at_10": r, "mrr": q}} for m in ("a", "b")}
                   for v, r, q in (("x", 0.5, 0.4), ("y", 0.5, 0.6), ("z", 0.6, 0.1))}
        self.assertEqual(benchmark.select_product_text(results, ["x", "y", "z"], ["a", "b"]), "z")
        self.assertEqual(benchmark.select_product_text(results, ["x", "y"], ["a", "b"]), "y")
        curve = {"5": 0.5, "10": 0.8, "20": 0.815, "40": 0.82}
        self.assertEqual(benchmark.select_candidate_count(curve, [5, 10, 20, 40]), 20)

    def test_load_queries_refuses_another_split(self):
        with self.assertRaises(ValueError):
            benchmark.load_queries(ROOT / CONFIG["data"]["retrieval_dev"], "test")

    def test_phase_7_reads_dev_only(self):
        self.assertEqual(CONFIG["evaluated_splits"], ["dev"])
        self.assertNotIn("retrieval_test", json.dumps(CONFIG["data"]))
        for script in ("evaluate_retrieval.py", "build_index.py"):
            self.assertNotIn("retrieval_test", (ROOT / "scripts" / script).read_text(encoding="utf-8"))
        rows = [json.loads(x) for x in (ROOT / CONFIG["outputs"]["predictions"].format(method="minilm"))
                .read_text(encoding="utf-8").splitlines()]
        self.assertEqual({r["query_id"] for r in rows}, {q["query_id"] for q in DEV})

    def test_committed_metrics_recompute_from_predictions(self):
        for method in CONFIG["methods"]:
            path = ROOT / CONFIG["outputs"]["predictions"].format(method=method)
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            summary = benchmark.summarize(rows, CONFIG["candidate_count"]["grid"])
            self.assertEqual(summary, METRICS["results"][method])

    def test_frozen_choices_follow_the_rules(self):
        sel = METRICS["selection"]
        table = sel["product_text"]["table"]
        results = {v: {m: {"summary": table[v][m]} for m in CONFIG["methods"]} for v in table}
        self.assertEqual(benchmark.select_product_text(results, CONFIG["product_text"]["candidates"],
                                                       CONFIG["methods"]), CONFIG["product_text"]["selected"])
        curve = sel["candidate_count"]["recall_at_k"][CONFIG["candidate_count"]["method"]]
        self.assertEqual(benchmark.select_candidate_count(curve, CONFIG["candidate_count"]["grid"]),
                         CONFIG["candidate_count"]["selected"])


class RebuildTests(unittest.TestCase):
    def test_retrieval_outputs_rebuild_identically(self):
        result = run_script("evaluate_retrieval.py", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_index_manifest_rebuilds_identically(self):
        result = run_script("build_index.py", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_scripts_follow_the_check_pattern(self):
        for script in ("evaluate_retrieval.py", "build_index.py"):
            self.assertIn("--check", (ROOT / "scripts" / script).read_text(encoding="utf-8"))
        self.assertIn("product_text", inspect.signature(retrieve_candidates).parameters)


if __name__ == "__main__":
    unittest.main()
