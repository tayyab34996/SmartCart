# Generates the five canonical acceptance benchmark scenarios for baseline pipeline evaluation
# Expected lines are hand-calculated from the pilot catalog (simulated PKR prices, minor units):
#   Homemade Pasta (foodcom_3474, base 4 servings): 240 g white_flour, 2 egg, 14.787 ml olive_oil, 59.148 ml water.
#   2 servings -> 120 g flour, 1 egg, 7.394 ml oil, 29.574 ml water; 6 servings -> 360 g, 3, 22.181 ml, 88.722 ml.
#   Packs: flour 500 g = 9000 (1000 g = 16000); egg 6 = 18000; oil 100 ml = 18000; water 500 ml = 5000;
#   chicken 500 g = 80000 (2 x 250 g = 90000).

def	_line(ingredient_id:str,product_id,pack_count:int,line_cost_minor:int)->dict:
	return	{'ingredient_id':ingredient_id,'product_id':product_id,'pack_count':pack_count,'line_cost_minor':line_cost_minor}

def	_pasta_lines(flour_line:dict)->list:
	return	[flour_line,_line('egg','sim_egg_6piece',1,18000),_line('olive_oil','sim_olive_oil_100ml',1,18000),_line('water','sim_water_500ml',1,5000)]

def	generate_baseline_reference_scenarios()->list:
	flour_one_pack=_line('white_flour','sim_flour_500g',1,9000)
	flour_from_pantry=_line('white_flour',None,0,0)
	return	[
		{'id':'d3_ref_01_feasible_recipe','description':'Standard_feasible_recipe_basket_under_budget','request':{'recipe_id':'foodcom_3474','servings':2,'budget_minor':100000},'expected_status':'valid','expected_max_cost_minor':100000,'expected_total_cost_minor':50000,'expected_lines':_pasta_lines(flour_one_pack)},
		{'id':'d3_ref_02_pantry_deduction','description':'Pantry_flour_250g_covers_120g_requirement_so_no_flour_is_bought','request':{'recipe_id':'foodcom_3474','servings':2,'pantry':{'white_flour':'250'},'budget_minor':100000},'expected_status':'valid','expected_max_cost_minor':100000,'expected_total_cost_minor':41000,'expected_lines':_pasta_lines(flour_from_pantry)},
		{'id':'d3_ref_03_budget_exceeded','description':'Recipe_with_insufficient_budget_flagging_over_budget','request':{'recipe_id':'foodcom_3474','servings':2,'budget_minor':20000},'expected_status':'over_budget','expected_total_cost_minor':50000,'expected_lines':_pasta_lines(flour_one_pack)},
		{'id':'d3_ref_04_direct_grocery_list','description':'Direct_ingredient_requirements_without_recipe','request':{'requirements':[{'ingredient_id':'chicken_breast','required_amount':'500','unit':'g'},{'ingredient_id':'olive_oil','required_amount':'100','unit':'ml'}],'budget_minor':150000},'expected_status':'valid','expected_max_cost_minor':150000,'expected_total_cost_minor':98000,'expected_lines':[_line('chicken_breast','sim_chicken_500g',1,80000),_line('olive_oil','sim_olive_oil_100ml',1,18000)]},
		{'id':'d3_ref_05_scaled_servings','description':'Recipe_scaled_to_six_servings_still_fits_one_pack_per_ingredient','request':{'recipe_id':'foodcom_3474','servings':6,'budget_minor':200000},'expected_status':'valid','expected_max_cost_minor':200000,'expected_total_cost_minor':50000,'expected_lines':_pasta_lines(flour_one_pack)}
	]
