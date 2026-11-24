# Normalizes extracted entity spans into validated typed slot values

def	normalize_slot_spans(spans:list)->dict:
	normalized={'servings':None,'budget_minor':None,'meal':None,'diet':None,'exclusions':[],'pantry':{}}
	word_num={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
	for	s	in	spans:
		lbl=s['label']
		txt=s['text'].strip().lower()
		if	lbl=='SERVINGS':
			if	txt.isdigit():
				normalized['servings']=int(txt)
			elif	txt	in	word_num:
				normalized['servings']=word_num[txt]
		elif	lbl=='BUDGET':
			cleaned=''.join(c	for	c	in	txt	if	c.isdigit())
			if	cleaned:
				normalized['budget_minor']=int(cleaned)*100
		elif	lbl=='MEAL':
			normalized['meal']=txt
		elif	lbl=='DIET':
			normalized['diet']=txt
		elif	lbl=='EXCLUSION':
			normalized['exclusions'].append(txt)
		elif	lbl=='PANTRY':
			normalized['pantry'][txt]=None
	return	normalized
