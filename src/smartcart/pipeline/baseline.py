# Executes baseline pipeline from natural language and structured requests into itemized baskets
from	decimal	import	Decimal
from	smartcart.data.contracts	import	requirements_for
from	smartcart.optimization.basket	import	assemble_independent_basket
from	smartcart.nlu.parser	import	parse_natural_language_request

def	build_baseline_basket_from_request(request:dict,catalog_data:dict)->dict:
	pantry_dict=request.get('pantry',{})
	if	'recipe_id'	in	request:
		reqs_raw=requirements_for(catalog_data,request['recipe_id'],request['servings'])
		requirements=[{'ingredient_id':r['ingredient_id'],'required_amount':Decimal(str(r['amount'])),'unit':r['unit'],'pantry_amount':Decimal(str(pantry_dict.get(r['ingredient_id'],'0')))}	for	r	in	reqs_raw]
	else:
		requirements=[{'ingredient_id':r['ingredient_id'],'required_amount':Decimal(str(r['required_amount'])),'unit':r['unit'],'pantry_amount':Decimal(str(pantry_dict.get(r['ingredient_id'],r.get('pantry_amount','0'))))}	for	r	in	request.get('requirements',[])]
	basket=assemble_independent_basket(requirements,catalog_data.get('products',[]),budget_minor=request.get('budget_minor'))
	return	{'request':request,'basket':basket}

def	run_baseline_pipeline(text:str,catalog_data:dict)->dict:
	structured=parse_natural_language_request(text,catalog_data.get('recipes',[]))
	if	structured.get('intent')=='unsupported':
		return	{'status':'unsupported','request':structured,'basket':None}
	res=build_baseline_basket_from_request(structured,catalog_data)
	return	{'status':res['basket']['status'],'request':structured,'basket':res['basket']}
