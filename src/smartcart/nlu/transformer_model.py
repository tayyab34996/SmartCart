# DistilBERT transformer models for intent classification and token slot tagging

import	os
os.environ['KMP_DUPLICATE_LIB_OK']='TRUE'
import	torch
from	transformers	import	AutoConfig,AutoModelForSequenceClassification,AutoModelForTokenClassification

def	build_distilbert_intent_model(num_labels:int=4,model_path:str=None):
	if	model_path	and	os.path.exists(model_path):
		return	AutoModelForSequenceClassification.from_pretrained(model_path)
	config=AutoConfig.for_model('distilbert',num_labels=num_labels,n_layers=2,n_heads=4,dim=128)
	return	AutoModelForSequenceClassification.from_config(config)

def	predict_distilbert_intent(model,input_ids:torch.Tensor,attention_mask:torch.Tensor=None)->dict:
	model.eval()
	with	torch.no_grad():
		outputs=model(input_ids=input_ids,attention_mask=attention_mask)
		logits=outputs.logits
		probs=torch.softmax(logits,dim=-1)[0]
		best_idx=int(torch.argmax(probs).item())
		confidence=float(probs[best_idx].item())
		return	{'predicted_class':best_idx,'confidence':confidence,'probabilities':probs.tolist()}

def	build_distilbert_slot_model(num_labels:int=9,model_path:str=None):
	if	model_path	and	os.path.exists(model_path):
		return	AutoModelForTokenClassification.from_pretrained(model_path)
	config=AutoConfig.for_model('distilbert',num_labels=num_labels,n_layers=2,n_heads=4,dim=128)
	return	AutoModelForTokenClassification.from_config(config)

def	predict_distilbert_slots(model,input_ids:torch.Tensor,attention_mask:torch.Tensor=None)->list:
	model.eval()
	with	torch.no_grad():
		outputs=model(input_ids=input_ids,attention_mask=attention_mask)
		logits=outputs.logits[0]
		pred_indices=torch.argmax(logits,dim=-1).tolist()
		return	pred_indices
