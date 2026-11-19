#Assembles_independent_basket_for_requirements_and_checks_total_cost_against_budget
from	decimal	import	Decimal
from	smartcart.optimization.selection	import	select_lowest_cost_option

def	assemble_independent_basket(requirements:list,candidates:list,budget_minor:int=None)->dict:
	lines=[select_lowest_cost_option(r['ingredient_id'],Decimal(str(r['required_amount'])),Decimal(str(r.get('pantry_amount','0'))),r['unit'],candidates)	for	r	in	requirements]
	total_cost=sum(line['line_cost_minor']	for	line	in	lines)
	is_over=budget_minor	is	not	None	and	total_cost>budget_minor
	status='over_budget'	if	is_over	else	'valid'
	remaining=budget_minor-total_cost	if	budget_minor	is	not	None	else	None
	return	{'status':status,'lines':lines,'total_cost_minor':total_cost,'budget_minor':budget_minor,'budget_remaining_minor':remaining,'item_count':len(lines)}
