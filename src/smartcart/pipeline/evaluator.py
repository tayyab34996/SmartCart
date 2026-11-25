# Evaluates a benchmark scenario through the baseline pipeline and verifies status, exact lines, total cost and pantry use
from	smartcart.pipeline.baseline	import	build_baseline_basket_from_request

LINE_FIELDS=('ingredient_id','product_id','pack_count','line_cost_minor')

def	_comparable_lines(lines:list)->list:
	return	[{k:line.get(k)	for	k	in	LINE_FIELDS}	for	line	in	lines]

def	evaluate_baseline_scenario(scenario:dict,catalog_data:dict)->dict:
	res=build_baseline_basket_from_request(scenario['request'],catalog_data)
	basket=res['basket']
	status=basket['status']
	actual_lines=_comparable_lines(basket['lines'])
	status_match=True	if	'expected_status'	not	in	scenario	else	(status==scenario['expected_status'])
	cost_match=True	if	'expected_max_cost_minor'	not	in	scenario	else	(basket['total_cost_minor']<=scenario['expected_max_cost_minor'])
	total_match=True	if	'expected_total_cost_minor'	not	in	scenario	else	(basket['total_cost_minor']==scenario['expected_total_cost_minor'])
	lines_match=True	if	'expected_lines'	not	in	scenario	else	(actual_lines==_comparable_lines(scenario['expected_lines']))
	pantry_match=not	basket['ignored_pantry_keys']
	success=status_match	and	cost_match	and	total_match	and	lines_match	and	pantry_match
	return	{'scenario_id':scenario.get('id',''),'status':status,'matches_expected_status':status_match,'within_expected_cost':cost_match,'matches_expected_total':total_match,'matches_expected_lines':lines_match,'pantry_keys_all_used':pantry_match,'ignored_pantry_keys':basket['ignored_pantry_keys'],'success':success,'total_cost_minor':basket['total_cost_minor'],'budget_remaining_minor':basket['budget_remaining_minor'],'item_count':basket['item_count'],'uncovered_ingredients':basket['uncovered_ingredients'],'lines':basket['lines']}
