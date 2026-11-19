# Classifies user query intent using keyword heuristic rules into supported intent classes
import	re

def	classify_intent_baseline(text:str)->str:
	lower_text=text.lower()
	tokens=set(re.findall(r'\w+',lower_text))
	if	tokens&{'cook','recipe','dinner','lunch','meal','breakfast','servings','serve'}:
		return	'plan_meal'
	if	tokens&{'add','remove','change','replace','update','revise'}:
		return	'revise_basket'
	if	tokens&{'buy','need','get','grocery','list','cart','items'}:
		return	'build_grocery_list'
	return	'unsupported'
