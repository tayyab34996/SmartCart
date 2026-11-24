# NLU evaluation runner comparing baseline and transformer models with failure case analysis

import	json
import	joblib
from	pathlib	import	Path
from	.dataset	import	generate_nlu_training_examples
from	.intent_model	import	train_intent_classifier,predict_intent_with_confidence
from	.slots	import	extract_slots_rule_based
from	.uncertainty	import	check_request_clarification
from	.evaluation	import	compute_intent_metrics,compute_slot_accuracy

def	generate_evaluation_benchmark_data()->tuple:
	train_data=generate_nlu_training_examples()
	val_data=[
		{'text':'cook\tpasta\tfor\t4','true_intent':'plan_meal','true_budget':None,'true_servings':4},
		{'text':'recipe\tfor\tsalad\tunder\t500','true_intent':'plan_meal','true_budget':50000,'true_servings':None},
		{'text':'buy\tmilk\tand\tbread','true_intent':'build_grocery_list','true_budget':None,'true_servings':None},
		{'text':'need\t2\tkg\tflour','true_intent':'build_grocery_list','true_budget':None,'true_servings':None},
		{'text':'change\tbudget\tto\t3000','true_intent':'revise_basket','true_budget':300000,'true_servings':None},
		{'text':'drop\teggs\tfrom\tcart','true_intent':'revise_basket','true_budget':None,'true_servings':None},
		{'text':'weather\ttoday','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'play\tsome\tmusic','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'cok\tpasta\tfast','true_intent':'plan_meal','true_budget':None,'true_servings':None},
		{'text':'dinner\tfor\tsix\tpeople','true_intent':'plan_meal','true_budget':None,'true_servings':6},
		{'text':'make\tcurry\tunder\t$25','true_intent':'plan_meal','true_budget':2500,'true_servings':None},
		{'text':'find\tcheap\tbreakfast','true_intent':'plan_meal','true_budget':None,'true_servings':None},
		{'text':'bue\teggz\tnow','true_intent':'build_grocery_list','true_budget':None,'true_servings':None},
		{'text':'add\tcheddar\tand\tbutter','true_intent':'build_grocery_list','true_budget':None,'true_servings':None},
		{'text':'get\t5\tapples','true_intent':'build_grocery_list','true_budget':None,'true_servings':None},
		{'text':'shopping\tlist\tfor\tbaking','true_intent':'build_grocery_list','true_budget':None,'true_servings':None},
		{'text':'remove\tflour\tand\tsalt','true_intent':'revise_basket','true_budget':None,'true_servings':None},
		{'text':'swap\tmilk\twith\talmond\tmilk','true_intent':'revise_basket','true_budget':None,'true_servings':None},
		{'text':'update\tbudget\t$100','true_intent':'revise_basket','true_budget':10000,'true_servings':None},
		{'text':'clear\teverything\tin\tcart','true_intent':'revise_basket','true_budget':None,'true_servings':None},
		{'text':'what\tis\tthe\ttime','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'who\twon\tthe\tworld\tcup','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'write\tpython\tscript','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'translate\tbonjour\tto\tenglish','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'tell\tme\ta\tjoke','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'search\tgoogle\tfor\tshoes','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'send\tan\temail\tto\tjohn','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'open\tyoutube\tvideo','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'call\tmom\ton\tphone','true_intent':'unsupported','true_budget':None,'true_servings':None},
		{'text':'set\talarm\tfor\t7\tam','true_intent':'unsupported','true_budget':None,'true_servings':None}
	]
	return	train_data,val_data

def	execute_nlu_benchmark(output_metrics_path:str=None,output_failures_path:str=None)->dict:
	train_data,val_data=generate_evaluation_benchmark_data()
	X_train=[x['text']for	x	in	train_data]
	y_train=[x['intent']for	x	in	train_data]
	model=train_intent_classifier(X_train,y_train)
	Path('models').mkdir(parents=True,exist_ok=True)
	joblib.dump(model,'models/nlu_intent_baseline.joblib')
	y_true=[]
	y_pred=[]
	true_slots=[]
	pred_slots=[]
	failures=[]
	for	item	in	val_data:
		txt=item['text']
		t_intent=item['true_intent']
		pred_info=predict_intent_with_confidence(model,txt)
		p_intent=pred_info['intent']
		conf=pred_info['confidence']
		raw_slots=extract_slots_rule_based(txt)
		b_min=(raw_slots['budget']*100)if	raw_slots['budget']is	not	None	else	None
		s_num=raw_slots['servings']
		clarify=check_request_clarification({'intent':p_intent,'budget_minor':b_min},confidence=conf)
		y_true.append(t_intent)
		y_pred.append(p_intent)
		true_slots.append({'budget_minor':item['true_budget'],'servings':item['true_servings']})
		pred_slots.append({'budget_minor':b_min,'servings':s_num})
		is_failure=(p_intent!=t_intent)or	clarify['needs_clarification']
		if	is_failure	or	len(failures)<20:
			reason_str='Intent_mismatch_or_low_confidence_ambiguity'if(p_intent!=t_intent)else'Triggered_uncertainty_clarification'
			failures.append({'query':txt,'true_intent':t_intent,'predicted_intent':p_intent,'confidence':conf,'needs_clarification':clarify['needs_clarification'],'clarification_type':clarify['clarification_type'],'reason':reason_str})
	intent_metrics=compute_intent_metrics(y_true,y_pred)
	slot_metrics=compute_slot_accuracy(true_slots,pred_slots)
	benchmark_results={'intent_metrics':intent_metrics,'slot_metrics':slot_metrics,'num_validation_samples':len(val_data),'num_failures_analyzed':len(failures)}
	if	output_metrics_path:
		Path(output_metrics_path).parent.mkdir(parents=True,exist_ok=True)
		with	open(output_metrics_path,'w')as	f:
			json.dump(benchmark_results,f,indent=2)
	if	output_failures_path:
		Path(output_failures_path).parent.mkdir(parents=True,exist_ok=True)
		with	open(output_failures_path,'w')as	f:
			json.dump(failures,f,indent=2)
	return	benchmark_results
