# Retrieval benchmark runner comparing TF-IDF and MiniLM FAISS under identical catalog and eligibility rules

import	json
from	pathlib	import	Path
from	.tfidf	import	build_tfidf_retriever,search_products_tfidf
from	.semantic	import	load_semantic_encoder,build_faiss_index,search_products_semantic
from	.filtering	import	filter_eligible_candidates
from	.evaluation	import	evaluate_retriever_queries
from	.queries	import	generate_retrieval_benchmark_queries

def	execute_retrieval_benchmark(catalog_path:str='data/processed/pilot/catalog.json',output_path:str=None)->dict:
	with	open(catalog_path,'r')as	f:
		catalog=json.load(f)
	products=catalog.get('products',[])
	dev_queries,test_queries=generate_retrieval_benchmark_queries(products)
	tfidf_state=build_tfidf_retriever(products)
	encoder=load_semantic_encoder()
	faiss_state=build_faiss_index(products,encoder)
	tfidf_fn=lambda	q:search_products_tfidf(q,tfidf_state,top_k=10)
	minilm_fn=lambda	q:search_products_semantic(q,faiss_state,encoder,top_k=10)
	dev_tfidf=evaluate_retriever_queries(dev_queries,tfidf_fn,filter_fn=filter_eligible_candidates)
	dev_minilm=evaluate_retriever_queries(dev_queries,minilm_fn,filter_fn=filter_eligible_candidates)
	test_tfidf=evaluate_retriever_queries(test_queries,tfidf_fn,filter_fn=filter_eligible_candidates)
	test_minilm=evaluate_retriever_queries(test_queries,minilm_fn,filter_fn=filter_eligible_candidates)
	results={'dev':{'tfidf':dev_tfidf,'minilm':dev_minilm},'test':{'tfidf':test_tfidf,'minilm':test_minilm}}
	if	output_path:
		Path(output_path).parent.mkdir(parents=True,exist_ok=True)
		with	open(output_path,'w')as	f:
			json.dump(results,f,indent=2)
	return	results
