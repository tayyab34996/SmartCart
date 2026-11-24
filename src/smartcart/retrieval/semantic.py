# Semantic product retrieval using frozen MiniLM embeddings and FAISS exact inner-product index

import	os
os.environ['KMP_DUPLICATE_LIB_OK']='TRUE'
import	numpy	as	np
import	faiss
from	sentence_transformers	import	SentenceTransformer

def	load_semantic_encoder(model_name:str='sentence-transformers/all-MiniLM-L6-v2')->SentenceTransformer:
	return	SentenceTransformer(model_name,local_files_only=True)

def	build_faiss_index(products:list,encoder:SentenceTransformer)->tuple:
	texts=[(str(p.get('name',''))+chr(32)+str(p.get('ingredient_id','')).replace('_',chr(32))).strip().lower()for	p	in	products]
	embeddings=encoder.encode(texts,normalize_embeddings=True,convert_to_numpy=True)
	vectors=np.asarray(embeddings,dtype='float32')
	faiss.normalize_L2(vectors)
	index=faiss.IndexFlatIP(vectors.shape[1])
	index.add(vectors)
	return	(index,products)

def	search_products_semantic(query:str,index_state:tuple,encoder:SentenceTransformer,top_k:int=10)->list:
	index,products=index_state
	if	not	products	or	not	query.strip():
		return	[]
	q_emb=encoder.encode([query.strip().lower()],normalize_embeddings=True,convert_to_numpy=True)
	q_vec=np.asarray(q_emb,dtype='float32')
	faiss.normalize_L2(q_vec)
	k=min(top_k,len(products))
	scores,indices=index.search(q_vec,k)
	results=[]
	for	score,idx	in	zip(scores[0],indices[0]):
		if	idx>=0:
			item=dict(products[int(idx)])
			item['retrieval_score']=float(score)
			results.append(item)
	return	results
