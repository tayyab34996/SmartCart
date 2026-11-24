# Evaluates parsed request for missing slots and determines if clarification questions are required

def	check_request_clarification(parsed:dict,recipes:list=None)->dict:
	intent=parsed.get('intent')
	if	intent=='unsupported':
		return	{'needs_clarification':False,'clarification_type':None,'prompt':None}
	if	intent=='plan_meal'	and	not	parsed.get('recipe_id'):
		avail=[r.get('name','')	for	r	in	(recipes	or	[])	if	r.get('name')]
		options_str=chr(44).join(avail[:3])	if	avail	else	'supported_recipes'
		return	{'needs_clarification':True,'clarification_type':'missing_recipe','prompt':'Which_recipe_would_you_like_to_cook:'+options_str}
	pantry=parsed.get('pantry',{})
	for	k,v	in	pantry.items():
		if	v	is	None	or	v=='':
			return	{'needs_clarification':True,'clarification_type':'missing_pantry_quantity','prompt':'How_much_'+k+'_do_you_already_have_in_your_pantry?'}
	return	{'needs_clarification':False,'clarification_type':None,'prompt':None}
