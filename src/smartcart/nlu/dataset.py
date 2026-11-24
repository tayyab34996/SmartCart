# Generates seed annotated dataset for intent classification and BIO token slot extraction

def	generate_nlu_training_examples()->list:
	return	[
		{'text':'cook\tpasta\tfor\t2\tpeople','intent':'plan_meal','tokens':['cook','pasta','for','2','people'],'tags':['O','B-MEAL','O','B-SERVINGS','O']},
		{'text':'recipe\tfor\tchicken\tunder\t1000','intent':'plan_meal','tokens':['recipe','for','chicken','under','1000'],'tags':['O','O','B-MEAL','O','B-BUDGET']},
		{'text':'buy\tflour\tand\teggs','intent':'build_grocery_list','tokens':['buy','flour','and','eggs'],'tags':['O','B-PRODUCT','O','B-PRODUCT']},
		{'text':'need\t500\tg\tof\trice','intent':'build_grocery_list','tokens':['need','500','g','of','rice'],'tags':['O','B-QUANTITY','B-UNIT','O','B-PRODUCT']},
		{'text':'change\tbudget\tto\t2000','intent':'revise_basket','tokens':['change','budget','to','2000'],'tags':['O','O','O','B-BUDGET']},
		{'text':'remove\tflour\tfrom\tcart','intent':'revise_basket','tokens':['remove','flour','from','cart'],'tags':['O','B-PRODUCT','O','O']},
		{'text':'what\tis\tthe\tcapital\tof\tfrance','intent':'unsupported','tokens':['what','is','the','capital','of','france'],'tags':['O','O','O','O','O','O']},
		{'text':'book\ta\tflight\tto\tlondon','intent':'unsupported','tokens':['book','a','flight','to','london'],'tags':['O','O','O','O','O']}
	]
