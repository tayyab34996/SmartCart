# Decodes a sequence of tokens and BIO tags into labeled entity span dictionaries

def	decode_bio_spans(tokens:list,tags:list)->list:
	spans=[]
	current_label=None
	current_tokens=[]
	current_start=None
	for	i,(token,tag)	in	enumerate(zip(tokens,tags)):
		if	tag.startswith('B-'):
			if	current_label:
				spans.append({'label':current_label,'text':chr(32).join(current_tokens),'start':current_start,'end':i})
			current_label=tag[2:]
			current_tokens=[token]
			current_start=i
		elif	tag.startswith('I-')	and	current_label==tag[2:]:
			current_tokens.append(token)
		else:
			if	current_label:
				spans.append({'label':current_label,'text':chr(32).join(current_tokens),'start':current_start,'end':i})
				current_label=None
				current_tokens=[]
				current_start=None
	if	current_label:
		spans.append({'label':current_label,'text':chr(32).join(current_tokens),'start':current_start,'end':len(tokens)})
	return	spans
