# Unit tests for TF-IDF, MiniLM FAISS semantic retrieval, eligibility filtering, and IR metrics

import	unittest
import	sys
from	pathlib	import	Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))

from	smartcart.data.contracts	import	load_pilot
from	smartcart.retrieval.tfidf	import	build_tfidf_retriever,search_products_tfidf
from	smartcart.retrieval.semantic	import	load_semantic_encoder,build_faiss_index,search_products_semantic
from	smartcart.retrieval.filtering	import	filter_eligible_candidates
from	smartcart.retrieval.evaluation	import	compute_query_retrieval_metrics,evaluate_retriever_queries
from	smartcart.retrieval.queries	import	generate_retrieval_benchmark_queries

class	TestRetrieval(unittest.TestCase):
	def	test_tfidf_and_semantic_retrieval(self):
		catalog=load_pilot(ROOT/'data'/'processed'/'pilot'/'catalog.json')
		products=catalog['products']
		tfidf_state=build_tfidf_retriever(products)
		res_lex=search_products_tfidf('chicken\tbreast',tfidf_state,top_k=5)
		self.assertTrue(len(res_lex)>0)
		encoder=load_semantic_encoder()
		faiss_state=build_faiss_index(products,encoder)
		res_sem=search_products_semantic('poultry\tfillet',faiss_state,encoder,top_k=5)
		self.assertEqual(res_sem[0]['ingredient_id'],'chicken_breast')

	def	test_eligibility_filter_strict_dietary(self):
		cands=[
			{'id':'p1','ingredient_id':'chicken_breast','pack_unit':'g','available':True,'dietary':{'vegetarian':'unknown'}},
			{'id':'p2','ingredient_id':'tofu','pack_unit':'g','available':True,'dietary':{'vegetarian':True}}
		]
		filtered=filter_eligible_candidates(cands,dietary_rules=['vegetarian'])
		self.assertEqual(len(filtered),1)
		self.assertEqual(filtered[0]['id'],'p2')

	def	test_retrieval_metrics_and_queries(self):
		m=compute_query_retrieval_metrics(['a','b','c'],{'b'})
		self.assertEqual(m['recall_at_5'],1.0)
		self.assertEqual(m['mrr'],0.5)
		catalog=load_pilot(ROOT/'data'/'processed'/'pilot'/'catalog.json')
		dev,test=generate_retrieval_benchmark_queries(catalog['products'])
		self.assertEqual(len(dev),50)
		self.assertEqual(len(test),100)

	def	test_evaluator_never_passes_gold_ingredient_to_filter(self):
		seen=[]
		def	recording_filter(cands,**kwargs):
			seen.append(kwargs)
			return	filter_eligible_candidates(cands,**kwargs)
		queries=[{'query':'x','required_ingredient':'egg','required_unit':None,'dietary_rules':None,'relevant_ids':['e1']}]
		evaluate_retriever_queries(queries,lambda	q:[],filter_fn=recording_filter)
		self.assertEqual(len(seen),1)
		self.assertNotIn('required_ingredient',seen[0])

	def	test_wrong_ingredient_ranked_first_is_penalised(self):
		ranking=[{'id':'flour1','ingredient_id':'white_flour','available':True},{'id':'egg1','ingredient_id':'egg','available':True}]
		queries=[{'query':'eggs','required_ingredient':'egg','relevant_ids':['egg1']}]
		result=evaluate_retriever_queries(queries,lambda	q:ranking,filter_fn=filter_eligible_candidates)
		self.assertEqual(result['mrr'],0.5)

	def	test_tfidf_ranks_whole_catalog_deterministically(self):
		catalog=load_pilot(ROOT/'data'/'processed'/'pilot'/'catalog.json')
		state=build_tfidf_retriever(catalog['products'])
		first=search_products_tfidf('zzzunmatchedterm',state,top_k=10)
		second=search_products_tfidf('zzzunmatchedterm',state,top_k=10)
		self.assertEqual(len(first),10)
		self.assertTrue(all(r['retrieval_score']==0.0	for	r	in	first))
		self.assertEqual([r['id']	for	r	in	first],sorted(r['id']	for	r	in	first))
		self.assertEqual([r['id']	for	r	in	first],[r['id']	for	r	in	second])

if	__name__=='__main__':
	unittest.main()
