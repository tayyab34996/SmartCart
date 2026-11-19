# Extracts structured slots such as servings, budget, and dietary terms using regular expressions
import	re

def	extract_slots_rule_based(text:str)->dict:
	lower_text=text.lower()
	servings_match=re.search(r'(\d+)\s*(?:servings?|people|persons)|for\s+(\d+)',lower_text)
	servings=int(servings_match.group(1)	or	servings_match.group(2))	if	servings_match	else	None
	budget_match=re.search(r'(?:budget|under|max|spend|limit)\s*(?:of|is|:)?\s*(?:pkr|rs\.?)?\s*(\d+)',lower_text)
	budget=int(budget_match.group(1))	if	budget_match	else	None
	diet_match=re.search(r'\b(vegetarian|vegan|gluten-free|dairy-free|halal)\b',lower_text)
	diet=diet_match.group(1)	if	diet_match	else	None
	return	{'servings':servings,'budget':budget,'diet':diet,'raw_text':text}
