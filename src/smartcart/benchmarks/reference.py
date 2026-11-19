# Generates the five canonical acceptance benchmark scenarios for baseline pipeline evaluation

def	generate_baseline_reference_scenarios()->list:
	return	[
		{'id':'d3_ref_01_feasible_recipe','description':'Standard_feasible_recipe_basket_under_budget','request':{'recipe_id':'foodcom_3474','servings':2,'budget_minor':100000},'expected_status':'valid','expected_max_cost_minor':100000},
		{'id':'d3_ref_02_pantry_deduction','description':'Recipe_with_pantry_stock_reducing_packs','request':{'recipe_id':'foodcom_3474','servings':2,'pantry':{'flour':'250'},'budget_minor':100000},'expected_status':'valid','expected_max_cost_minor':100000},
		{'id':'d3_ref_03_budget_exceeded','description':'Recipe_with_insufficient_budget_flagging_over_budget','request':{'recipe_id':'foodcom_3474','servings':2,'budget_minor':20000},'expected_status':'over_budget'},
		{'id':'d3_ref_04_direct_grocery_list','description':'Direct_ingredient_requirements_without_recipe','request':{'requirements':[{'ingredient_id':'chicken_breast','required_amount':'500','unit':'g'},{'ingredient_id':'olive_oil','required_amount':'100','unit':'ml'}],'budget_minor':150000},'expected_status':'valid','expected_max_cost_minor':150000},
		{'id':'d3_ref_05_scaled_servings','description':'Recipe_scaled_to_six_servings_testing_multi_pack','request':{'recipe_id':'foodcom_3474','servings':6,'budget_minor':200000},'expected_status':'valid','expected_max_cost_minor':200000}
	]
