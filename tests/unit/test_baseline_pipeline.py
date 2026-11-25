# Unit tests for the D3 simple baseline pipeline, NLU parser, and benchmark evaluator
import	unittest
import	sys
from	pathlib	import	Path
from	copy	import	deepcopy

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))

from	smartcart.data.contracts	import	load_pilot
from	smartcart.pipeline.baseline	import	run_baseline_pipeline
from	smartcart.retrieval.lexical	import	search_products_lexical
from	smartcart.benchmarks.reference	import	generate_baseline_reference_scenarios
from	smartcart.pipeline.benchmark	import	run_baseline_benchmark
from	smartcart.pipeline.evaluator	import	evaluate_baseline_scenario
from	smartcart.pipeline.baseline	import	build_baseline_basket_from_request

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

	def	_scenario(self,scenario_id):
		return	next(s	for	s	in	generate_baseline_reference_scenarios()	if	s['id']==scenario_id)

	def	test_pantry_stock_reduces_purchased_flour(self):
		plain=evaluate_baseline_scenario(self._scenario('d3_ref_01_feasible_recipe'),self.data)
		pantry=evaluate_baseline_scenario(self._scenario('d3_ref_02_pantry_deduction'),self.data)
		plain_flour=next(l	for	l	in	plain['lines']	if	l['ingredient_id']=='white_flour')
		pantry_flour=next(l	for	l	in	pantry['lines']	if	l['ingredient_id']=='white_flour')
		self.assertEqual(plain_flour['pack_count'],1)
		self.assertEqual(pantry_flour['pack_count'],0)
		self.assertEqual(pantry_flour['line_status'],'covered_by_pantry')
		self.assertLess(pantry['total_cost_minor'],plain['total_cost_minor'])
		self.assertEqual(pantry['ignored_pantry_keys'],[])

	def	test_wrong_expected_line_fails_scenario(self):
		scen=deepcopy(self._scenario('d3_ref_01_feasible_recipe'))
		scen['expected_lines'][0]['pack_count']=2
		result=evaluate_baseline_scenario(scen,self.data)
		self.assertTrue(result['matches_expected_status'])
		self.assertFalse(result['matches_expected_lines'])
		self.assertFalse(result['success'])

	def	test_wrong_expected_total_fails_scenario(self):
		scen=deepcopy(self._scenario('d3_ref_04_direct_grocery_list'))
		scen['expected_total_cost_minor']=97999
		result=evaluate_baseline_scenario(scen,self.data)
		self.assertFalse(result['matches_expected_total'])
		self.assertFalse(result['success'])

	def	test_unmatched_pantry_key_is_reported_and_fails(self):
		scen=deepcopy(self._scenario('d3_ref_02_pantry_deduction'))
		scen['request']['pantry']={'flour':'250'}
		result=evaluate_baseline_scenario(scen,self.data)
		self.assertEqual(result['ignored_pantry_keys'],['flour'])
		self.assertFalse(result['success'])

	def	test_missing_product_option_gives_incomplete_basket(self):
		request={'requirements':[{'ingredient_id':'olive_oil','required_amount':'100','unit':'ml'},{'ingredient_id':'saffron','required_amount':'1','unit':'g'}],'budget_minor':100000}
		basket=build_baseline_basket_from_request(request,self.data)['basket']
		self.assertEqual(basket['status'],'incomplete')
		self.assertEqual(basket['uncovered_ingredients'],['saffron'])
		saffron=next(l	for	l	in	basket['lines']	if	l['ingredient_id']=='saffron')
		self.assertEqual(saffron['line_status'],'no_compatible_option')
		self.assertIsNone(saffron['product_id'])

if	__name__=='__main__':
	unittest.main()
