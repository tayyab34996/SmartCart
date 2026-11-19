# Runs a collection of baseline benchmark scenarios and exports evaluation metrics
import	json
from	pathlib	import	Path
from	smartcart.data.contracts	import	load_pilot
from	smartcart.benchmarks.reference	import	generate_baseline_reference_scenarios
from	smartcart.pipeline.evaluator	import	evaluate_baseline_scenario

def	run_baseline_benchmark(scenarios:list,catalog_data:dict)->dict:
	results=[evaluate_baseline_scenario(s,catalog_data)	for	s	in	scenarios]
	passed_count=sum(1	for	r	in	results	if	r['success'])
	total_cost=sum(r['total_cost_minor']	for	r	in	results)
	return	{'total_scenarios':len(scenarios),'passed':passed_count,'failed':len(scenarios)-passed_count,'total_cost_minor':total_cost,'results':results}

def	export_baseline_benchmark_results(catalog_path:str,output_path:str='results/predictions/baseline_outputs.json')->dict:
	data=load_pilot(Path(catalog_path))
	scenarios=generate_baseline_reference_scenarios()
	bench=run_baseline_benchmark(scenarios,data)
	out_file=Path(output_path)
	out_file.parent.mkdir(parents=True,exist_ok=True)
	out_file.write_text(json.dumps(bench,indent=2,default=str),encoding='utf-8')
	return	bench
