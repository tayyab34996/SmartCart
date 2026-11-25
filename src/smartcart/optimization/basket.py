#Assembles_independent_basket_for_requirements_and_checks_total_cost_against_budget
from	decimal	import	Decimal
from	smartcart.optimization.selection	import	select_lowest_cost_option
from	smartcart.recipes.quantities	import	missing_amount

def	_build_line(requirement:dict,candidates:list)->dict:
	ing=requirement['ingredient_id']
	unit=requirement['unit']
	required=Decimal(str(requirement['required_amount']))
	pantry=Decimal(str(requirement.get('pantry_amount','0')))
	missing=missing_amount(required,pantry)
	if	missing==0:
		return	{'ingredient_id':ing,'line_status':'covered_by_pantry','product_id':None,'missing_amount':missing,'pack_count':0,'line_cost_minor':0,'surplus_amount':Decimal(0),'unit':unit,'currency':None}
	try:
		option=select_lowest_cost_option(ing,required,pantry,unit,candidates)
	except	ValueError:
		return	{'ingredient_id':ing,'line_status':'no_compatible_option','product_id':None,'missing_amount':missing,'pack_count':0,'line_cost_minor':0,'surplus_amount':Decimal(0),'unit':unit,'currency':None}
	return	{'ingredient_id':ing,'line_status':'selected',**option}

def	assemble_independent_basket(requirements:list,candidates:list,budget_minor:int=None)->dict:
	lines=[_build_line(r,candidates)	for	r	in	requirements]
	total_cost=sum(line['line_cost_minor']	for	line	in	lines)
	uncovered=[line['ingredient_id']	for	line	in	lines	if	line['line_status']=='no_compatible_option']
	is_over=budget_minor	is	not	None	and	total_cost>budget_minor
	if	uncovered:
		status='incomplete'
	elif	is_over:
		status='over_budget'
	else:
		status='valid'
	remaining=budget_minor-total_cost	if	budget_minor	is	not	None	else	None
	return	{'status':status,'lines':lines,'uncovered_ingredients':uncovered,'total_cost_minor':total_cost,'budget_minor':budget_minor,'budget_remaining_minor':remaining,'item_count':sum(1	for	line	in	lines	if	line['line_status']=='selected')}
