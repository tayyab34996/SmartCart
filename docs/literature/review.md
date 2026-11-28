# Literature review — 15-paper comparison and synthesis (D1)

Status: **complete (Phase 12, 2026-11-28).**

## Sources and rules

- **Starting point:** the team's literature matrix,
  [`SmartCart_Literature_Review.xlsx`](SmartCart_Literature_Review.xlsx) (prepared
  6 October 2026). It lists 15 papers with venue, method, data, evaluation, findings and
  the evidence inspected for each, plus a gap synthesis and the search notes.
- **Venue and recency rule (decided by the team, 2026-11-28):** peer-reviewed conference
  or journal papers from 2019–2025. Sentence-BERT (2019) is kept as the foundational
  reference for the retrieval component. The lecture's own venue list was not available;
  the venue column below lets it be checked. Findings and demonstration tracks are named
  as such.
- **Reading depth.** For the five closest papers named in the build plan — constrained
  food QA [S7], the next-basket reality check [S8], Sentence-BERT [S10], ChatCRS [S11]
  and ReCANet [S12] — and for TIFU-KNN [S9], the methods and results sections were read
  in full in Phase 12 (author or publisher PDFs). For the other nine, the cells come from
  the matrix's recorded evidence (publisher metadata and abstracts; method and results
  sections where the matrix says so). A cell is filled only from the paper; numbers from
  different papers are not comparable, because the tasks and datasets differ.
- **No novelty claim.** The review supports a tested integration for the stated scope. It
  does not show that no earlier system combines these components; no exhaustive novelty
  search was done.

## Comparison table

Rows 1–6 are cited as [S7]–[S12] and rows 7–15 as [L7]–[L15] in the report. The matrix's
own IDs differ: rows 1–15 are matrix P09, P03, P13, P15, P01, P06, P02, P04, P05, P07,
P08, P10, P11, P12 and P14.

| # | Paper | Venue / track | Task | Constraints handled | Method | Data | Evaluation | Relation to SmartCart |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Chen, Subburathinam, Chen, Zaki 2021 — Personalized Food Recommendation as Constrained Question Answering over a Large-scale Food Knowledge Graph [S7] | ACM WSDM 2021, main conference | Return every recipe in a food KG that satisfies a question plus the user's preferences and health guidelines | Dish type, required and excluded ingredients (likes, allergies), cuisine, nutrient ranges from ADA guidelines; **no budget, quantities or purchasable products** | pFoodReQ: query expansion with personal constraints, symbolic KG augmentation for numeric ranges, constraint-tag embeddings for negation, on a BAMnet KBQA model | FoodKG (about 1M recipes); 8,430 template-generated questions (56 templates) with simulated preferences; 727 out-of-domain test questions | Macro-F1, MAP, MAR, human ratings. pFoodReQ F1 63.7 vs 41.2 for the best personalised baseline; removing query expansion drops F1 to 4.2 | **Closest constraint-aware work.** Like SmartCart it turns a request into explicit requirements and uses template-generated questions; unlike SmartCart it returns recipes, not a priced basket of whole packs under a budget, and does not prove infeasibility |
| 2 | Li, Jullien, Ariannezhad, de Rijke 2023 — A Next Basket Recommendation Reality Check [S8] | ACM TOIS 41(4), journal | Re-evaluate next-basket recommendation methods | None (purchase prediction) | Splits performance into **repeat** and **explore** items; new metrics (RepR/ExplR, Recall_rep/Recall_expl, PHR); compares frequency, nearest-neighbour and deep methods | TaFeng, Dunnhumby, Instacart (repeat ratio 0.597) | Recall, NDCG, PHR at basket sizes 10 and 20; on Instacart Recall@10 TIFU-KNN 0.360, P-TopFreq 0.326; repeat items give over 97% of repeat-biased methods' performance on Instacart and Dunnhumby | Motivates Track B's **separate repeat and new-item metrics** and the personal-frequency baseline; SmartCart's main task (fulfil a stated meal) is different from predicting the next basket |
| 3 | Hu, He, Gao, Zhang 2020 — Modeling Personalized Item Frequency Information for Next-basket Recommendation [S9] | ACM SIGIR 2020, main conference | Next-basket prediction | None | TIFU-KNN: time-decayed personal item-frequency vectors, blended with nearest-neighbour users | ValuedShopper, Instacart, Dunnhumby, TaFeng | Recall@10/20, NDCG@10/20; on Instacart Recall@10 0.395 vs 0.302 for Sets2Sets; a personal top-frequency baseline beats several neural methods | Source of SmartCart's **personal-frequency ranker** in Track B, which beats popularity there by +0.221 NDCG@10 |
| 4 | Reimers, Gurevych 2019 — Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks [S10] | EMNLP-IJCNLP 2019, main conference (foundational exception) | Sentence embeddings for semantic similarity and search | None | Siamese/triplet fine-tuning of BERT with mean pooling, compared by cosine similarity | SNLI and MultiNLI for training; STS, SentEval, Wikipedia sections | Spearman correlation on STS (76.55 average unsupervised for the large NLI model); finding the most similar pair in 10,000 sentences falls from about 65 hours with BERT to about 5 seconds | Foundation of SmartCart's **MiniLM retriever** (a sentence-transformers model) with an exact FAISS index; SmartCart tests it on short grocery queries against TF-IDF |
| 5 | Li, Deng, Hu, Kan, Li 2025 — ChatCRS: Incorporating External Knowledge and Goal Guidance for LLM-based Conversational Recommender Systems [S11] | Findings of NAACL 2025 (Findings track) | LLM-based conversational recommendation | Dialogue goals; no budget, quantity or dietary hard constraints | Training-free framework: a tool-augmented knowledge-retrieval agent over KG triples and a fine-tuned goal-planning agent feed an LLM | DuRecDial (10k dialogues), TG-ReDial | NDCG@10/50, MRR, BLEU/F1, human ratings; on DuRecDial NDCG@10 0.549 vs 0.024 for few-shot ChatGPT; informativeness 1.76 vs 1.50 | Supports **grounding answers in structured data and asking for missing information**; SmartCart asks typed clarification questions and grounds every output in the catalog and a validator rather than an LLM |
| 6 | Ariannezhad, Jullien, Li, Fang, Schelter, de Rijke 2022 — ReCANet: A Repeat Consumption-Aware Neural Network for Next Basket Recommendation in Grocery Shopping [S12] | ACM SIGIR 2022, main conference | Grocery next-basket prediction | None | Models each (user, previously bought item) pair with user/item embeddings and a purchase-gap history through stacked LSTMs | Instacart, Dunnhumby, ValuedShopper and three proprietary datasets | Recall and NDCG at 10 and basket size; on Instacart Recall@10 0.359 vs 0.343 for TIFU-KNN; over 54% of recall comes from repeat items on average | Confirms that **repeat purchases dominate grocery history**; ReCANet recommends only previously bought items, which is why SmartCart keeps a content-based path for meal requests and reports new items separately |
| 7 | Chen, Xiao, Zhang, Luo, Lian, Liu 2024 — M3-Embedding | Findings of ACL 2024 (Findings track) | Multilingual, multi-granularity text retrieval | None | One model for dense, sparse and multi-vector retrieval, trained with self-knowledge distillation | Multilingual, cross-lingual and long-document retrieval benchmarks | Retrieval quality across languages and lengths | A possible stronger retriever for SmartCart's unsolved **transliterated queries** (kali mirch, makhan); not tested |
| 8 | Romanov, Lashinin, Ananyeva, Kolesnikov 2023 — Time-Aware Item Weighting for the Next Basket Recommendations | ACM RecSys 2023, main conference | Next-basket prediction | None | TAIW: item-specific temporal patterns with a neighbourhood module (Hawkes-process inspired) | Dunnhumby, TaFeng, TaoBao | NDCG@K, Recall@K, ablations | A time-aware alternative to the frequency baseline; SmartCart's Track B uses order position only, not timing |
| 9 | Wang, Tang, Zhao, Wang, Wen 2023 — Rethinking the Evaluation for Conversational Recommendation in the Era of LLMs | EMNLP 2023, main conference | Evaluating conversational recommenders | None | iEvaLM: LLM-based user simulators for interactive evaluation | Two public conversational recommendation datasets | Interactive evaluation, explainability | SmartCart also uses a **simulated user** (one scripted answer, at most three questions) but checks every final basket deterministically |
| 10 | Wang, Zhou, Wen, Zhao 2022 — Towards Unified Conversational Recommender Systems via Knowledge-Enhanced Prompt Learning | ACM KDD 2022, main conference | Joint recommendation and response generation | None | UniCRS: knowledge-enhanced prompts over a fixed language model | Two public conversational recommendation datasets | Recommendation and conversation metrics | Architecture reference for keeping dialogue and product representations aligned; SmartCart keeps them separate (parser → structured request → selector) |
| 11 | Tian, Zhang, Guo, Huang, Metoyer, Chawla 2022 — RecipeRec: A Heterogeneous Graph Learning Model for Recipe Recommendation | IJCAI 2022, main conference | Recipe recommendation | None (preference only) | User–recipe–ingredient graph with hierarchical attention, an ingredient set transformer and contrastive learning | URI-Graph | Recipe recommendation against competing methods | Motivates **ingredient-level relations**; SmartCart uses simpler ingredient-level association rules, which turned out not to help |
| 12 | Jannach, Manzoor, Cai, Chen 2021 — A Survey on Conversational Recommender Systems | ACM Computing Surveys 54(5), journal survey | Survey | — | Taxonomy of interaction, knowledge and evaluation | Prior work | Review of evaluation practice | Frames clarification and feedback as part of recommendation; SmartCart defines success operationally (valid complete basket, proven infeasibility, clarification within three turns) |
| 13 | Zhou, Wang, Zhou, Shang, Cheng, Zhao, Li, Wen 2021 — CRSLab: An Open-Source Toolkit for Building Conversational Recommender System | ACL-IJCNLP 2021, **System Demonstrations** track | Toolkit for conversational recommendation | — | Modular framework, 19 models, automatic evaluation | Six annotated CRS datasets | Automatic and human evaluation interfaces | Supports SmartCart's **modular, swap-one-component comparison** and shared evaluation scripts |
| 14 | Qin, Liu, Che, Kang, Zhao, Liu 2021 — A Co-Interactive Transformer for Joint Slot Filling and Intent Detection | IEEE ICASSP 2021 | Joint intent detection and slot filling | Slots only | Bidirectional co-interactive transformer | SNIPS, ATIS | Intent accuracy, slot F1, overall accuracy | Supports joint intent and slot models; SmartCart trains separate DistilBERT intent and slot models and compares them with a rule/dictionary baseline |
| 15 | Karpukhin, Oğuz, Min, Lewis, Wu, Edunov, Chen, Yih 2020 — Dense Passage Retrieval for Open-Domain Question Answering | EMNLP 2020, main conference | Dense retrieval for QA | None | Dual encoder trained on question–passage pairs | Open-domain QA benchmarks | Top-20 retrieval accuracy (9–19 points over BM25), end-to-end QA | Supports dense retrieval against a lexical baseline; SmartCart finds the same direction on short grocery queries (Recall@10 0.764 vs 0.610) |

## Synthesis

**1. Food and grocery recommendation under constraints.** The closest work, pFoodReQ
[S7], treats personalised food recommendation as constrained question answering: it
expands a question with the user's likes, allergies and nutrient guidelines and returns
every recipe in a knowledge graph that satisfies them. Its benchmark, like SmartCart's, is
template-generated, and its ablations show that making constraints explicit matters most
(removing query expansion collapses F1 from 63.7 to 4.2). Recipe models such as RecipeRec
(#11) learn user–recipe–ingredient relations. Neither line of work turns a chosen dish
into a purchasable set of products in whole packs, subtracts a pantry, enforces a total
budget, or states when no valid basket exists — the part SmartCart evaluates.

**2. Next-basket recommendation and repeat purchases.** Grocery histories are dominated
by repeat purchases: ReCANet [S12] reports that over half of recall comes from repeat
items, and the reality check [S8] finds repeat items behind over 97% of repeat-biased
methods' performance on Instacart. Simple personal-frequency baselines are therefore
strong [S8], [S9]; TIFU-KNN [S9] builds on them, and ReCANet and TAIW (#8) improve on them
by a few per cent. SmartCart's Track B follows this practice — personal frequency as the
baseline to beat, repeat and new items reported separately — and finds the same: personal
frequency beats popularity by a wide margin, and an association term does not improve on
it.

**3. Semantic retrieval.** Sentence-BERT [S10] made sentence embeddings practical for
similarity search, and dense retrievers such as DPR (#15) outperform lexical BM25 on
question answering. M3-Embedding (#7) extends this to many languages. These results come
from general text; SmartCart measures the effect on short grocery queries with synonyms,
brands, misspellings and Urdu transliterations, where MiniLM beats TF-IDF but neither
handles the transliterations.

**4. Conversational recommendation and clarification.** Surveys and systems (#12, #10,
#13) treat asking questions and taking feedback as part of recommendation. ChatCRS [S11]
grounds an LLM in retrieved knowledge and planned dialogue goals, and iEvaLM (#9) argues
for interactive evaluation with simulated users. Joint intent and slot models (#14)
extract structure from requests. SmartCart uses typed clarification questions (missing
dish, budget, pantry or item quantity, ambiguous diet), a simulated user with one answer
and at most three questions, and a deterministic validator for every final basket, so
conversational fluency is never counted as success on its own.

**5. Gap.** In the 15 reviewed papers, no work evaluates **complete, quantity-aware,
budget-constrained baskets built from free-text requests**, scored against the user's
annotated constraints and compared with independent item ranking with post-hoc filtering.
The food-constraint work [S7] stops at recipes; next-basket work [S8], [S9], [S12]
predicts purchases without a stated goal or hard constraints; retrieval and
conversational work evaluate matching or dialogue quality. This is a gap in the reviewed
literature, not a claim that no such system exists.

## Implementation sources (cited, not part of the 15)

- [S1] Instacart Market Basket Analysis — dataset access and provider terms
- [S2] Food.com Recipes and Reviews — irkaal dataset card
- [S3] scikit-learn — common pitfalls and data leakage
- [S4] Hugging Face Transformers — token classification guide
- [S5] Sentence Transformers — all-MiniLM-L6-v2 model card
- [S6] Google OR-Tools — CP-SAT solver and status handling
