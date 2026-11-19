#Evaluates_candidate_products_for_an_ingredient_and_selects_lowest_cost_option_with_deterministic_tie_breaker
from	decimal	import	Decimal
from	smartcart.optimization.options	import	evaluate_product_option

def	select_lowest_cost_option(ingredient_id:str,required_amount:Decimal,pantry_amount:Decimal,unit:str,candidates:list)->dict:
	eligible=[p	for	p	in	candidates	if	p.get('ingredient_id')==ingredient_id	and	p.get('pack_unit')==unit	and	p.get('available',True)]
	if	not	eligible:
		raise	ValueError('No_compatible_available_product_option_found')
	evaluated=[evaluate_product_option(ingredient_id,required_amount,pantry_amount,unit,p)	for	p	in	eligible]
	return	min(evaluated,key=lambda	e:(e['line_cost_minor'],e['surplus_amount'],e['product_id']))
