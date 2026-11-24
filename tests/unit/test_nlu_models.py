# Unit tests for NLU intent models, DistilBERT architectures, evaluation metrics, and uncertainty detection

import	unittest
import	sys
from	pathlib	import	Path
import	torch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))

from	smartcart.nlu.dataset	import	generate_nlu_training_examples
from	smartcart.nlu.intent_model	import	train_intent_classifier,predict_intent_with_confidence
from	smartcart.nlu.evaluation	import	compute_intent_metrics,compute_slot_span_f1,compute_slot_accuracy
from	smartcart.nlu.transformer_model	import	build_distilbert_intent_model,predict_distilbert_intent,build_distilbert_slot_model,predict_distilbert_slots
from	smartcart.nlu.uncertainty	import	check_request_clarification
from	smartcart.nlu.normalization	import	normalize_slot_spans

class	TestNLUModels(unittest.TestCase):
	def	test_intent_pipeline_training_and_prediction(self):
		data=generate_nlu_training_examples()
		texts=[x['text']for	x	in	data]
		labels=[x['intent']for	x	in	data]
		pipeline=train_intent_classifier(texts,labels)
		res=predict_intent_with_confidence(pipeline,'cook\tpasta')
		self.assertIn('intent',res)
		self.assertIn('confidence',res)
		self.assertGreaterEqual(res['confidence'],0.0)
		self.assertLessEqual(res['confidence'],1.0)

	def	test_slot_span_f1_computation(self):
		true_spans=[[{'label':'MEAL','start':1,'end':2}]]
		pred_spans=[[{'label':'MEAL','start':1,'end':2}]]
		metrics=compute_slot_span_f1(true_spans,pred_spans)
		self.assertEqual(metrics['f1'],1.0)
		self.assertEqual(metrics['precision'],1.0)
		self.assertEqual(metrics['recall'],1.0)

	def	test_distilbert_forward_passes(self):
		intent_model=build_distilbert_intent_model(num_labels=4)
		dummy_input=torch.tensor([[101,7592,102]])
		pred=predict_distilbert_intent(intent_model,dummy_input)
		self.assertIn('predicted_class',pred)
		self.assertIn('confidence',pred)
		slot_model=build_distilbert_slot_model(num_labels=9)
		slot_preds=predict_distilbert_slots(slot_model,dummy_input)
		self.assertEqual(len(slot_preds),3)

	def	test_uncertainty_and_normalization(self):
		clarify_yes=check_request_clarification({'budget_minor':None},confidence=0.4)
		self.assertTrue(clarify_yes['needs_clarification'])
		clarify_no=check_request_clarification({'intent':'plan_meal','recipe_id':'pasta_01'},confidence=0.95)
		self.assertFalse(clarify_no['needs_clarification'])
		norm=normalize_slot_spans([{'label':'BUDGET','text':'$50'},{'label':'SERVINGS','text':'four'}])
		self.assertEqual(norm['budget_minor'],5000)
		self.assertEqual(norm['servings'],4)

if	__name__=='__main__':
	unittest.main()
