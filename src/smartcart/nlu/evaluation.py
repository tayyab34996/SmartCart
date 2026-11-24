# Evaluation metrics for intent classification, BIO entity-level slot F1, and normalization accuracy

from	sklearn.metrics	import	f1_score,accuracy_score,confusion_matrix

def	compute_intent_metrics(y_true:list,y_pred:list)->dict:
	acc=float(accuracy_score(y_true,y_pred))
	macro_f1=float(f1_score(y_true,y_pred,average='macro',zero_division=0))
	labels=sorted(list(set(y_true)|set(y_pred)))
	cm=confusion_matrix(y_true,y_pred,labels=labels).tolist()
	return	{'accuracy':acc,'macro_f1':macro_f1,'labels':labels,'confusion_matrix':cm}

def	compute_slot_span_f1(true_spans_list:list,pred_spans_list:list)->dict:
	tp=0
	fp=0
	fn=0
	for	t_spans,p_spans	in	zip(true_spans_list,pred_spans_list):
		t_set=set((s['label'],s['start'],s['end'])for	s	in	t_spans)
		p_set=set((s['label'],s['start'],s['end'])for	s	in	p_spans)
		tp+=len(t_set&p_set)
		fp+=len(p_set-t_set)
		fn+=len(t_set-p_set)
	prec=float(tp/(tp+fp))if(tp+fp)>0	else	0.0
	rec=float(tp/(tp+fn))if(tp+fn)>0	else	0.0
	f1=float(2*prec*rec/(prec+rec))if(prec+rec)>0	else	0.0
	return	{'precision':prec,'recall':rec,'f1':f1,'true_positives':tp,'false_positives':fp,'false_negatives':fn}

def	compute_slot_accuracy(true_slots_list:list,pred_slots_list:list)->dict:
	total=len(true_slots_list)
	if	total==0:
		return	{'budget_accuracy':1.0,'servings_accuracy':1.0}
	budget_correct=sum(1	for	t,p	in	zip(true_slots_list,pred_slots_list)if	t.get('budget_limit')==p.get('budget_limit'))
	servings_correct=sum(1	for	t,p	in	zip(true_slots_list,pred_slots_list)if	t.get('servings')==p.get('servings'))
	return	{'budget_accuracy':float(budget_correct/total),'servings_accuracy':float(servings_correct/total)}
