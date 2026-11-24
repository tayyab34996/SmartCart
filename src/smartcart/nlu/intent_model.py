# TF-IDF and calibrated LinearSVC intent classification pipeline with confidence estimation

from	sklearn.feature_extraction.text	import	TfidfVectorizer
from	sklearn.svm	import	LinearSVC
from	sklearn.calibration	import	CalibratedClassifierCV
from	sklearn.pipeline	import	Pipeline

def	build_intent_pipeline()->Pipeline:
	base_svc=LinearSVC(dual='auto',random_state=42)
	calibrated_clf=CalibratedClassifierCV(estimator=base_svc,cv=2)
	vectorizer=TfidfVectorizer(ngram_range=(1,2),lowercase=True)
	return	Pipeline([('tfidf',vectorizer),('clf',calibrated_clf)])

def	train_intent_classifier(texts:list,labels:list)->Pipeline:
	pipeline=build_intent_pipeline()
	pipeline.fit(texts,labels)
	return	pipeline

def	predict_intent_with_confidence(pipeline:Pipeline,text:str)->dict:
	probabilities=pipeline.predict_proba([text])[0]
	best_idx=int(probabilities.argmax())
	best_intent=str(pipeline.classes_[best_idx])
	confidence=float(probabilities[best_idx])
	class_probs={str(cls):float(prob)for	cls,prob	in	zip(pipeline.classes_,probabilities.tolist())}
	return	{'intent':best_intent,'confidence':confidence,'probabilities':class_probs}
