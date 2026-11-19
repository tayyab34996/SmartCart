# Evaluates a benchmark scenario through the baseline pipeline and verifies expected status
from	smartcart.pipeline.baseline	import	build_baseline_basket_from_request

def	evaluate_baseline_scenario(scenario:dict,catalog_data:dict)->dict:
	res=build_baseline_basket_from_request(scenario['request'],catalog_data)
	basket=res['basket']
	status=basket['status']
	status_match=True	if	'expected_status'	not	in	scenario	else	(status==scenario['expected_status'])
	cost_match=True	if	'expected_max_cost_minor'	not	in	scenario	else	(basket['total_cost_minor']<=scenario['expected_max_cost_minor'])
	success=status_match	and	cost_match
	return	{'scenario_id':scenario.get('id',''),'status':status,'matches_expected_status':status_match,'within_expected_cost':cost_match,'success':success,'total_cost_minor':basket['total_cost_minor'],'budget_remaining_minor':basket['budget_remaining_minor'],'item_count':basket['item_count'],'lines':basket['lines']}
