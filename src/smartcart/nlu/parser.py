# Parses a natural language user request by extracting intent, slots, and matching recipe targets
from	smartcart.nlu.intent	import	classify_intent_baseline
from	smartcart.nlu.slots	import	extract_slots_rule_based

def	parse_natural_language_request(text:str,recipes:list=None)->dict:
	intent=classify_intent_baseline(text)
	slots=extract_slots_rule_based(text)
	matched_recipe_id=None
	if	recipes	and	intent=='plan_meal':
		lower_text=text.lower()
		for	r	in	recipes:
			recipe_name=r.get('name','').lower()
			tokens=set(recipe_name.split())
			if	tokens	and	any(t	in	lower_text	for	t	in	tokens	if	len(t)>3):
				matched_recipe_id=r.get('id')
				break
	servings=slots.get('servings')	or	2
	budget=slots.get('budget')
	budget_minor=budget*100	if	budget	is	not	None	else	None
	structured={'intent':intent,'servings':servings,'budget_minor':budget_minor,'raw_text':text}
	if	matched_recipe_id:
		structured['recipe_id']=matched_recipe_id
	return	structured
