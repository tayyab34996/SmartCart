# Unit tests for the D3 simple baseline pipeline, NLU parser, and benchmark evaluator
import	unittest
import	sys
from	pathlib	import	Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))

from	smartcart.data.contracts	import	load_pilot
from	smartcart.pipeline.baseline	import	run_baseline_pipeline
from	smartcart.retrieval.lexical	import	search_products_lexical
from	smartcart.benchmarks.reference	import	generate_baseline_reference_scenarios
from	smartcart.pipeline.benchmark	import	run_baseline_benchmark

class	BaselinePipelineTests(unittest.TestCase):
	@classmethod
	def	setUpClass(cls):
		cls.data=load_pilot(ROOT/'data/processed/pilot/catalog.json')

	def	test_end_to_end_baseline_recipe_request(self):
		out=run_baseline_pipeline('cook\tpasta\tfor\t2\tpeople\twith\tbudget\t1000',self.data)
		self.assertEqual(out['status'],'valid')
		self.assertEqual(len(out['basket']['lines']),4)
		self.assertEqual(out['basket']['total_cost_minor'],50000)

	def	test_end_to_end_baseline_over_budget(self):
		out=run_baseline_pipeline('cook\tpasta\tfor\t2\twith\tbudget\t200',self.data)
		self.assertEqual(out['status'],'over_budget')

	def	test_unsupported_intent_handling(self):
		out=run_baseline_pipeline('tell\tme\ta\tjoke\tabout\tweather',self.data)
		self.assertEqual(out['status'],'unsupported')
		self.assertIsNone(out['basket'])

	def	test_lexical_search_finds_product(self):
		matches=search_products_lexical('flour',self.data['products'],top_k=3)
		self.assertTrue(len(matches)>0)
		self.assertEqual(matches[0]['ingredient_id'],'white_flour')

	def	test_all_reference_benchmark_scenarios_pass(self):
		scens=generate_baseline_reference_scenarios()
		summary=run_baseline_benchmark(scens,self.data)
		self.assertEqual(summary['total_scenarios'],5)
		self.assertEqual(summary['passed'],5)
		self.assertEqual(summary['failed'],0)

if	__name__=='__main__':
	unittest.main()
