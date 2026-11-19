#Retrieves_top_k_matching_products_for_a_text_query_using_token_lexical_similarity
import	re

def	search_products_lexical(query:str,products:list,top_k:int=5)->list:
	query_tokens=set(re.findall(r'\w+',query.lower()))
	if	not	query_tokens:
		return	[]
	scored=[]
	for	p	in	products:
		text=(p.get('name','')+'\t'+p.get('ingredient_id','')+'\t'+p.get('id','')).lower()
		prod_tokens=set(re.findall(r'\w+',text))
		overlap=len(query_tokens&prod_tokens)
		if	overlap>0:
			score=overlap/len(query_tokens|prod_tokens)
			scored.append((score,p))
	scored.sort(key=lambda	x:(-x[0],x[1].get('id','')))
	return	[item[1]	for	item	in	scored[:top_k]]
