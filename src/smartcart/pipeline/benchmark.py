# Runs a collection of baseline benchmark scenarios and aggregates evaluation metrics
from	smartcart.pipeline.evaluator	import	evaluate_baseline_scenario

def	run_baseline_benchmark(scenarios:list,catalog_data:dict)->dict:
	results=[evaluate_baseline_scenario(s,catalog_data)	for	s	in	scenarios]
	passed_count=sum(1	for	r	in	results	if	r['success'])
	total_cost=sum(r['total_cost_minor']	for	r	in	results)
	return	{'total_scenarios':len(scenarios),'passed':passed_count,'failed':len(scenarios)-passed_count,'total_cost_minor':total_cost,'results':results}
