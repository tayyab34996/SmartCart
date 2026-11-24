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
from	smartcart.retrieval.evaluation	import	compute_query_retrieval_metrics
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

if	__name__=='__main__':
	unittest.main()
