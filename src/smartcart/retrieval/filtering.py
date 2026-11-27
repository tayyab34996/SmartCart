# Filters retrieved product candidates by availability, ingredient identity, units, and explicit dietary rules
# A diet is satisfied only by the catalog value "allowed"; "unknown" and "disallowed" fail (Phase 7 fix).

def	filter_eligible_candidates(candidates:list,required_ingredient:str=None,required_unit:str=None,dietary_rules:list=None)->list:
	eligible=[]
	for	p	in	candidates:
		if	not	p.get('available',True):
			continue
		if	required_ingredient	and	p.get('ingredient_id')!=required_ingredient:
			continue
		if	required_unit	and	p.get('pack_unit')!=required_unit:
			continue
		if	dietary_rules:
			diet_map=p.get('dietary',{})
			if	not	all(diet_map.get(rule)=='allowed'	for	rule	in	dietary_rules):
				continue
		eligible.append(p)
	return	eligible
