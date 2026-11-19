#Executes_baseline_pipeline_for_structured_request_and_assembles_itemized_basket
from	decimal	import	Decimal
from	smartcart.data.contracts	import	requirements_for
from	smartcart.optimization.basket	import	assemble_independent_basket

def	build_baseline_basket_from_request(request:dict,catalog_data:dict)->dict:
	pantry_dict=request.get('pantry',{})
	if	'recipe_id'	in	request:
		reqs_raw=requirements_for(catalog_data,request['recipe_id'],request['servings'])
		requirements=[{'ingredient_id':r['ingredient_id'],'required_amount':Decimal(str(r['amount'])),'unit':r['unit'],'pantry_amount':Decimal(str(pantry_dict.get(r['ingredient_id'],'0')))}	for	r	in	reqs_raw]
	else:
		requirements=[{'ingredient_id':r['ingredient_id'],'required_amount':Decimal(str(r['required_amount'])),'unit':r['unit'],'pantry_amount':Decimal(str(pantry_dict.get(r['ingredient_id'],r.get('pantry_amount','0'))))}	for	r	in	request.get('requirements',[])]
	basket=assemble_independent_basket(requirements,catalog_data.get('products',[]),budget_minor=request.get('budget_minor'))
	return	{'request':request,'basket':basket}
