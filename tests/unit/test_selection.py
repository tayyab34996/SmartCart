#Unit_tests_for_lowest_cost_product_selection_among_alternatives
import	unittest
import	sys
from	decimal	import	Decimal
from	pathlib	import	Path
from	copy	import	deepcopy

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))

from	smartcart.optimization.selection	import	select_lowest_cost_option

class	SelectionTests(unittest.TestCase):
	def	setUp(self):
		self.cand_250={'id':'p_250','ingredient_id':'chicken_breast','pack_amount':'250','pack_unit':'g','price_minor':45000,'currency':'PKR','available':True}
		self.cand_500={'id':'p_500','ingredient_id':'chicken_breast','pack_amount':'500','pack_unit':'g','price_minor':80000,'currency':'PKR','available':True}

	def	test_cheapest_option_is_selected(self):
		cands=[deepcopy(self.cand_250),deepcopy(self.cand_500)]
		actual=select_lowest_cost_option('chicken_breast',Decimal('600'),Decimal('200'),'g',cands)
		self.assertEqual(actual['product_id'],'p_500')
		self.assertEqual(actual['line_cost_minor'],80000)
		self.assertEqual(actual['pack_count'],1)

	def	test_tie_breaker_uses_lowest_surplus(self):
		p1={'id':'opt_a','ingredient_id':'rice','pack_amount':'500','pack_unit':'g','price_minor':10000,'currency':'PKR','available':True}
		p2={'id':'opt_b','ingredient_id':'rice','pack_amount':'600','pack_unit':'g','price_minor':10000,'currency':'PKR','available':True}
		actual=select_lowest_cost_option('rice',Decimal('500'),Decimal('0'),'g',[p1,p2])
		self.assertEqual(actual['product_id'],'opt_a')
		self.assertEqual(actual['surplus_amount'],Decimal('0'))

	def	test_tie_breaker_uses_alphabetical_id_when_cost_and_surplus_equal(self):
		p_beta={'id':'p_beta','ingredient_id':'salt','pack_amount':'100','pack_unit':'g','price_minor':5000,'currency':'PKR','available':True}
		p_alpha={'id':'p_alpha','ingredient_id':'salt','pack_amount':'100','pack_unit':'g','price_minor':5000,'currency':'PKR','available':True}
		actual=select_lowest_cost_option('salt',Decimal('100'),Decimal('0'),'g',[p_beta,p_alpha])
		self.assertEqual(actual['product_id'],'p_alpha')

	def	test_no_compatible_candidate_raises_error(self):
		with	self.assertRaises(ValueError):
			select_lowest_cost_option('chicken_breast',Decimal('100'),Decimal('0'),'kg',[deepcopy(self.cand_250)])
		with	self.assertRaises(ValueError):
			unavail=deepcopy(self.cand_250)
			unavail['available']=False
			select_lowest_cost_option('chicken_breast',Decimal('100'),Decimal('0'),'g',[unavail])

	def	test_candidates_are_not_mutated(self):
		cands=[deepcopy(self.cand_250),deepcopy(self.cand_500)]
		orig=deepcopy(cands)
		select_lowest_cost_option('chicken_breast',Decimal('600'),Decimal('200'),'g',cands)
		self.assertEqual(cands,orig)

if	__name__=='__main__':
	unittest.main()
