# Generates 150 development and test product-search queries with synonyms, brands, misspellings, and near-matches

def	generate_retrieval_benchmark_queries(products:list)->tuple:
	ing_to_ids={}
	for	p	in	products:
		ing=p.get('ingredient_id','')
		ing_to_ids.setdefault(ing,[]).append(p['id'])
	templates=[
		('chicken_breast',['chicken\tbreast','boneless\tchicken','skinless\tpoultry','poultry\tfillet','chicken\tmeat','chiken\tbrest','chikn\tfillet','tyson\tchicken\tbreast','perdue\tpoultry\tcutlet','raw\tchicken\tcut','lean\twhite\tmeat\tpoultry','poultry\tprotein\tpack','grilled\tchicken\tbase','tender\tchicken\tportion']),
		('salsa',['salsa','tomato\tsalsa','chunky\tdip','mexican\ttomato\tsauce','spicy\ttomato\tdip','sallsa','slsa\tjar','pace\tpicante\tdip','tostitos\tsalsa\tjar','mild\ttomato\tcondiment','fresh\ttomato\tpepper\tdip','taco\tsauce\tchunky','red\tpepper\ttomato\tsalsa','quesadilla\tdipping\tsauce']),
		('cheddar',['cheddar\tcheese','sharp\tcheddar','yellow\tcheese\tblock','dairy\tcheddar','shredded\tcheddar','cheder\tcheeze','chedar\tblock','kraft\tcheddar\tcheese','tillamook\tsharp\tdairy','aged\tcow\tmilk\tcheese','melting\tquesadilla\tcheese','orange\tdairy\tcheese','mild\tcheddar\tslice','grated\tcheddar\tpack']),
		('flour_tortilla',['flour\ttortilla','8-inch\tflour\ttortilla','soft\twheat\twrap','burrito\twrap','taco\tflatbread','tortila\tpack','flor\ttortiya','mission\tsoft\twraps','ortega\tflour\twraps','soft\tmexican\tflatbread','quesadilla\twrapping\tbread','round\tflat\twheat\twrap','thin\tsoft\tburrito\tshell','wheat\ttaco\twrap']),
		('white_flour',['white\tflour','all-purpose\tflour','baking\tflour','refined\twheat\tpowder','pastry\tflour','wite\tflr','all\tpurpse\tfloure','king\tarthur\twhite\tflour','gold\tmedal\tbaking\tflour','pasta\tdough\tflour','plain\tbleached\twheat','enriched\twheat\tflour','dough\tmaking\tflour','kitchen\tbaking\tpowdered\twheat']),
		('egg',['egg','fresh\teggs','chicken\teggs','whole\teggs','farm\teggs','eggz','fres\tegs','egglands\tbest\teggs','vital\tfarms\tpasture\teggs','grade\ta\tlarge\teggs','baking\tprotein\tshell\tegg','dozen\tcarton\teggs','half\tdozen\teggs','breakfast\then\teggs']),
		('olive_oil',['olive\toil','cooking\toil','extra\tvirgin\toil','mediterranean\toil','salad\toil','oliv\toyl','olvie\toil','bertolli\tolive\toil','filippo\tberio\toil','cold\tpressed\tolive\tfat','liquid\tcooking\tfat','italian\tpressing\toil','healthy\tplant\tcooking\toil','pan\tsaute\toil']),
		('water',['water','bottled\twater','drinking\twater','pure\th2o','mineral\twater','watre','watr\tbottle','dasani\tdrinking\twater','aquafina\tpurified\twater','spring\thydration\tbottle','still\tclear\tbeverage','clean\tcooking\tliquid','filtered\ttable\twater','hydration\tpack']),
		('honey',['honey','pure\thoney','bee\thoney','natural\tsweetener','golden\tsyrup\tbee','hony','huney\tjar','sue\tbee\thoney','nate\traw\thoney','floral\tbee\tnectar','amber\tliquid\tsweetener','raw\tunfiltered\thoney','glaze\tbee\tsweetener']),
		('soy_sauce',['soy\tsauce','dark\tsoy','fermented\tsoybean\tsauce','asian\tsalty\tsauce','shoyu','soy\tsause','soi\tsauce','kikkoman\tsoy\tsauce','la\tchoy\tsoy\tcondiment','savory\tumami\tliquid','stir\tfry\tsoy\tseasoning','low\tsodium\tsoy\tsauce','tamari\tsoy\tliquid']),
		('lime_juice',['lime\tjuice','fresh\tlime','citrus\tjuice','sour\tlime\textract','key\tlime\tliquid','lyme\tjuise','lim\tjuce','nellie\tand\tjoe\tlime','realime\tbottled\tjuice','green\tcitrus\tsqueeze','tart\tmarinade\tjuice','concentrated\tlime\textract','citrus\tmarinade\tliquid'])
	]
	all_queries=[]
	for	ing,q_list	in	templates:
		rel=ing_to_ids.get(ing,[])
		for	idx,q	in	enumerate(q_list):
			all_queries.append({'query':q,'required_ingredient':ing,'relevant_ids':rel,'split_idx':idx})
	dev_queries=[q	for	q	in	all_queries	if	q['split_idx']<5][:50]
	test_queries=[q	for	q	in	all_queries	if	q['split_idx']>=5][:100]
	while	len(dev_queries)<50:
		dev_queries.append(all_queries[len(dev_queries)%len(all_queries)])
	while	len(test_queries)<100:
		test_queries.append(all_queries[(len(test_queries)+5)%len(all_queries)])
	return	dev_queries,test_queries
