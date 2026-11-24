# TF-IDF cosine similarity product retriever baseline

from	sklearn.feature_extraction.text	import	TfidfVectorizer
from	sklearn.metrics.pairwise	import	cosine_similarity

def	_format_product_text(product:dict)->str:
	name=str(product.get('name',''))
	ing=str(product.get('ingredient_id','')).replace('_',chr(32))
	return	(name+chr(32)+ing).strip().lower()

def	build_tfidf_retriever(products:list)->tuple:
	corpus=[_format_product_text(p)for	p	in	products]
	vectorizer=TfidfVectorizer(ngram_range=(1,2),lowercase=True)
	matrix=vectorizer.fit_transform(corpus)
	return	(vectorizer,matrix,products)

def	search_products_tfidf(query:str,retriever_state:tuple,top_k:int=10)->list:
	vectorizer,matrix,products=retriever_state
	if	not	products	or	not	query.strip():
		return	[]
	q_vec=vectorizer.transform([query.strip().lower()])
	sims=cosine_similarity(q_vec,matrix)[0]
	ranked_indices=sims.argsort()[::-1][:top_k]
	results=[]
	for	idx	in	ranked_indices:
		score=float(sims[idx])
		if	score>0.0:
			item=dict(products[idx])
			item['retrieval_score']=score
			results.append(item)
	return	results
