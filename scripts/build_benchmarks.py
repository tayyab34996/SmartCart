"""Build the Phase 4 benchmarks: NLU annotations, basket scenarios and retrieval queries.

Usage:
  .venv\\Scripts\\python scripts\\build_benchmarks.py            # write all benchmark files and checks
  .venv\\Scripts\\python scripts\\build_benchmarks.py --check    # rebuild in memory; compare files and lock hashes
  .venv\\Scripts\\python scripts\\build_benchmarks.py --lock     # record SHA-256 hashes in docs/benchmark_lock.md

Every basket label comes from the gold feasibility checker. Splits are grouped: meal
families for NLU and baskets, ingredients for retrieval. The test files are locked after
review; `--check` fails if any locked file no longer matches its recorded hash.
"""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smartcart.benchmarks.build import (  # noqa: E402
    LIST_DESIGNS, PLAN_DESIGNS, FamilyBank, gold_for, list_spec, nice_quantity, plan_spec, resolve_clarification,
    stable_rng,
)
from smartcart.benchmarks.groups import SPLITS, split_ingredients, split_meal_families  # noqa: E402
from smartcart.benchmarks.language import choice  # noqa: E402
from smartcart.benchmarks.requests import (  # noqa: E402
    LIST_CATEGORIES, LIST_EXCLUDED, UNSUPPORTED_ACTS, Vocabulary, apply_revision, excludable, list_quantity, render,
)
from smartcart.data.contracts import load_catalog, requirements_for  # noqa: E402
from smartcart.nlu.spans import decode_bio_spans  # noqa: E402
from smartcart.validation.feasibility import DIETS, check_feasibility  # noqa: E402

LOCK_PATH = ROOT / "docs" / "benchmark_lock.md"


def dump(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def jsonl(rows) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def weighted(rng, weights: dict[str, float]) -> str:
    r, total = rng.random(), 0.0
    for key, w in weights.items():
        total += w
        if r < total:
            return key
    return key


# ---------------------------------------------------------------- NLU
def plan_or_list(vocab, bank, rng, family, category, split, start=None):
    """Try designs in rotation from ``start`` (random when None) until one applies."""
    designs = (PLAN_DESIGNS if family in bank.recipe_ids else LIST_DESIGNS)[category]
    offset = int(rng.random() * len(designs)) if start is None else start
    for attempt in range(len(designs)):
        design = designs[(offset + attempt) % len(designs)]
        if family in bank.recipe_ids:
            spec = plan_spec(vocab, family, design, rng, split)
        else:
            spec = list_spec(vocab, family, bank.lists[family], design, rng, split)
        if spec:
            return spec
    return None


REVISION_TYPES = ["budget", "servings", "exclusion", "pantry", "diet", "item", "budget_vague"]


def revision_spec(vocab, bank, rng, seed_id, split, k):
    kind = REVISION_TYPES[k % len(REVISION_TYPES)]
    families = bank.recipe_ids if kind in {"servings", "pantry", "exclusion"} else bank.families()
    base = None
    while base is None or base["design"] in {"pantry_full"}:
        base = plan_or_list(vocab, bank, rng, choice(rng, families), "feasible", split)
    session = gold_for({**base, "request_id": f"{seed_id}-session"}, vocab)
    rev = {"type": kind}
    if kind == "budget":
        rev["budget"] = choice(rng, [800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000])
    elif kind == "servings":
        rev["servings"] = choice(rng, [n for n in (2, 3, 4, 5, 6, 8) if n != base["servings"]])
    elif kind == "exclusion":
        pool = [i for i in excludable(vocab, base["recipe_id"]) if i not in session["exclusions"]]
        if not pool:
            return revision_spec(vocab, bank, rng, seed_id, split, k)
        rev["ingredient_id"] = choice(rng, pool)
    elif kind == "diet":
        rev["diet"] = choice(rng, list(DIETS))
    elif kind == "pantry":
        servings = base["servings"] or vocab.recipes[base["recipe_id"]]["base_servings"]
        lines = [l for l in requirements_for(vocab.catalog, base["recipe_id"], servings)
                 if l["ingredient_id"] not in session["pantry"]]
        counts = Counter(l["ingredient_id"] for l in lines)
        for line in lines:
            picked = counts[line["ingredient_id"]] == 1 and nice_quantity(rng, line["unit"], Decimal(line["amount"]), "partial")
            if picked:
                rev["entry"] = {"ingredient_id": line["ingredient_id"], "quantity": str(picked[0]), "user_unit": picked[1]}
                break
        if "entry" not in rev:
            rev = {"type": "budget", "budget": 2000}
    elif kind == "item":
        pool = sorted(i for i, cat in vocab.category.items() if cat in LIST_CATEGORIES and i not in LIST_EXCLUDED
                      and i in {line["ingredient_id"] for rid in bank.recipe_ids
                                for line in vocab.recipes[rid]["ingredients"]})
        iid = choice(rng, pool)
        q, u = list_quantity(rng, iid, vocab)
        rev["entry"] = {"ingredient_id": iid, "quantity": str(q), "user_unit": u}
    return {"intent": "revise_basket", "split": split, "family_id": base["family_id"], "design": f"revise_{rev['type']}",
            "revision": rev, "session": session, "suggestions": [], "pantry": [], "items": []}


def nlu_examples(vocab, banks, config):
    seed = config["seed"]
    examples, seeds = [], {s: [] for s in SPLITS}
    for split in SPLITS:
        counts, bank = config["nlu_seeds"][split], banks[split]
        acts = UNSUPPORTED_ACTS[split]
        if len(acts) != counts["unsupported"]:
            raise ValueError(f"{split}: {len(acts)} unsupported acts, config asks for {counts['unsupported']}")
        specs = []
        for kind, count, families in (("plan", counts["plan_meal"], bank.recipe_ids),
                                      ("list", counts["build_grocery_list"], sorted(bank.lists))):
            turn = Counter()  # rotates designs within each category so every design is represented
            for k in range(count):
                rng = stable_rng(seed, split, f"nlu-{kind}", k)
                spec, tries = None, 0
                while spec is None:
                    category = weighted(rng, config["nlu_design_weights"])
                    spec = plan_or_list(vocab, bank, rng, families[(k + tries) % len(families)], category, split,
                                        start=turn[category])
                    turn[category] += 1
                    tries += 1
                specs.append((f"{split}-{kind}-{k:03d}", spec))
        for k in range(counts["revise_basket"]):
            seed_id = f"{split}-revise-{k:03d}"
            specs.append((seed_id, revision_spec(vocab, bank, stable_rng(seed, split, "nlu-revise", k), seed_id, split, k)))
        for k, act in enumerate(acts):
            specs.append((f"{split}-unsupported-{k:03d}", {"intent": "unsupported", "split": split, "family_id": None,
                                                           "design": "unsupported", "act": act}))
        for seed_id, spec in specs:
            seeds[split].append(seed_id)
            texts = set()
            for j in range(config["paraphrases_per_seed"]):
                for attempt in range(40):
                    rendered = render(spec, stable_rng(seed, seed_id, j, attempt), vocab)
                    if rendered["text"] not in texts:
                        break
                texts.add(rendered["text"])
                ex_id = f"{seed_id}-p{j}"
                full = {**spec, "request_id": ex_id}
                gold = apply_revision(spec["session"], full, vocab) if spec["intent"] == "revise_basket" \
                    else gold_for(full, vocab)
                examples.append({"id": ex_id, "seed_id": seed_id, "split": split, "family_id": spec["family_id"],
                                 "intent": spec["intent"], "design": spec["design"], **rendered,
                                 "session": spec.get("session"), "gold": gold})
    return examples, seeds


# ---------------------------------------------------------------- baskets
def basket_scenarios(vocab, bank, split, targets, config):
    seed = config["seed"]
    families = bank.families()
    scenarios, discarded, seen = [], Counter(), set()
    for category in ("feasible", "infeasible", "clarification"):
        # Every (family, design) pair, in a seeded order; later passes reuse pairs with new draws.
        pairs = [(f, d) for f in families for d in (PLAN_DESIGNS if f in bank.recipe_ids else LIST_DESIGNS)[category]]
        pairs.sort(key=lambda p: sha(f"{seed}:{split}:{category}:{p[0]}:{p[1]}"))
        made, i = 0, 0
        while made < targets[category]:
            if i > 20 * len(pairs):
                raise RuntimeError(f"could not reach {targets[category]} {category} scenarios in {split}")
            family, design = pairs[i % len(pairs)]
            rng = stable_rng(seed, split, "basket", family, design, i)
            i += 1
            spec = plan_spec(vocab, family, design, rng, split) if family in bank.recipe_ids else \
                list_spec(vocab, family, bank.lists[family], design, rng, split)
            if spec is None:
                discarded["design_not_applicable"] += 1
                continue
            scenario_id = f"{split}_b{len(scenarios):03d}"
            gold = gold_for({**spec, "request_id": scenario_id}, vocab)
            key = json.dumps({k: v for k, v in gold.items() if k not in {"request_id", "clarification_prompt"}},
                             sort_keys=True)
            if key in seen:
                discarded["duplicate_request"] += 1
                continue
            result = check_feasibility(gold, vocab.catalog)
            if result["label"] != category:
                discarded[f"label_{result['label']}_not_{category}"] += 1
                continue
            answer, resolved_gold, resolved_result = None, None, None
            if category == "clarification":
                answer, resolved = resolve_clarification(spec, vocab, rng)
                resolved_gold = gold_for({**resolved, "request_id": scenario_id}, vocab)
                resolved_result = summarise(check_feasibility(resolved_gold, vocab.catalog))
            seen.add(key)
            rendered = render(spec, rng, vocab)
            scenarios.append({
                "scenario_id": scenario_id, "family_id": spec["family_id"], "label": category, "design": design,
                "text": rendered["text"], "gold_request": gold, "checker": summarise(result),
                "clarification_answer": answer, "resolved_request": resolved_gold, "resolved_checker": resolved_result,
                "has_history": False,
            })
            made += 1
    return scenarios, dict(discarded)


def summarise(result: dict) -> dict:
    keep = ("label", "reason", "min_cost_minor", "budget_minor", "basket", "ingredients_without_option",
            "options_per_line")
    out = {k: result[k] for k in keep if k in result}
    if "resolved" in result:
        out["covered_by_pantry"] = [l["ingredient_id"] for l in result["resolved"]["covered_by_pantry"]]
        out["excluded_lines"] = [l["ingredient_id"] for l in result["resolved"]["excluded_lines"]]
        out["required_ingredients"] = sorted({l["ingredient_id"] for l in result["resolved"]["lines"]})
    return out


def load_history(config) -> dict[int, set[str]]:
    import pandas as pd
    paths = {k: ROOT / v for k, v in config["instacart"].items()}
    if not paths["baskets"].is_file():
        raise SystemExit(f"missing {paths['baskets']}: run scripts/prepare_transactions.py first")
    trackb = json.loads(paths["trackb"].read_text(encoding="utf-8"))["users"]
    train_orders = {o for split in trackb.values() for o in split["train"]}
    mapping = pd.read_csv(paths["mapping"], usecols=["instacart_product_id", "ingredient_id"])
    baskets = pd.read_csv(paths["baskets"], usecols=["user_id", "order_id", "product_id"])
    baskets = baskets[baskets["order_id"].isin(train_orders)]
    joined = baskets.merge(mapping, left_on="product_id", right_on="instacart_product_id")
    return {int(u): set(g) for u, g in joined.groupby("user_id")["ingredient_id"]}


def assign_history(scenarios, count, history, config, split):
    seed, need = config["seed"], config["history_min_shared_ingredients"]
    order = sorted(scenarios, key=lambda s: sha(f"{seed}:history:{s['scenario_id']}"))
    users = sorted(history)
    assigned = 0
    for scenario in order:
        if assigned == count:
            break
        checker = scenario["resolved_checker"] or scenario["checker"]
        wanted = set(checker.get("required_ingredients") or
                     [i["ingredient_id"] for i in scenario["gold_request"]["items"]])
        candidates = [u for u in users if len(history[u] & wanted) >= need]
        if not candidates:
            continue
        user = min(candidates, key=lambda u: sha(f"{seed}:{split}:{scenario['scenario_id']}:{u}"))
        scenario["has_history"] = True
        scenario["gold_request"]["user_id"] = user
        if scenario["resolved_request"]:
            scenario["resolved_request"]["user_id"] = user
        scenario["history_shared_ingredients"] = sorted(history[user] & wanted)
        assigned += 1
    if assigned != count:
        raise RuntimeError(f"{split}: only {assigned} of {count} history scenarios found")


# ---------------------------------------------------------------- retrieval
def retrieval_sets(catalog, rows, groups, counts):
    out = {s: [] for s in ("dev", "test")}
    for row in rows:
        split = groups[row["ingredient_id"]]
        rules = [d for d in row["dietary_rules"].split("|") if d]
        unit = row["required_unit"] or None
        relevant = sorted(p["id"] for p in catalog["products"]
                          if p["ingredient_id"] == row["ingredient_id"] and p["available"]
                          and (unit is None or p["pack_unit"] == unit)
                          and all(p["dietary"][d] == "allowed" for d in rules))
        if not relevant:
            raise ValueError(f"query {row['query']!r} has no relevant product")
        out[split].append({"query_id": f"rq_{split}_{len(out[split]):03d}", "query": row["query"],
                           "required_ingredient": row["ingredient_id"], "query_type": row["query_type"],
                           "required_unit": unit, "dietary_rules": rules, "relevant_ids": relevant})
    for split, n in counts.items():
        if len(out[split]) != n:
            raise ValueError(f"retrieval {split}: {len(out[split])} queries, expected {n}")
    return out


# ---------------------------------------------------------------- checks
def span_consistency(example) -> list[str]:
    problems = []
    decoded = decode_bio_spans(example["tokens"], example["bio_tags"])
    if [d["label"] for d in decoded] != [s["label"] for s in example["spans"]]:
        problems.append("bio_does_not_decode_to_spans")
    gold = example["gold"]
    for span in example["spans"]:
        label, value = span["label"], span["value"]
        if label == "MEAL" and value != gold["recipe_id"]:
            problems.append("meal_value")
        if label == "SERVINGS" and value != gold["servings"]:
            problems.append("servings_value")
        if label == "BUDGET" and value * 100 != gold["budget_minor"]:
            problems.append("budget_value")
        if label == "PRODUCT" and value not in {i["ingredient_id"] for i in gold["items"]}:
            problems.append("product_value")
        if label == "PANTRY" and value not in gold["pantry"]:
            problems.append("pantry_value")
        if label == "EXCLUSION" and value not in gold["exclusions"]:
            problems.append("exclusion_value")
        if label == "DIET" and value != "ambiguous" and value not in gold["diet"]:
            problems.append("diet_value")
        if label in {"QUANTITY", "UNIT"}:
            target = span["attach_to"]
            if target is None or example["spans"][target]["label"] not in {"PRODUCT", "PANTRY"}:
                problems.append("unattached_quantity")
    return problems


def build_all(config):
    catalog = load_catalog(ROOT / config["catalog"])
    aliases = {}
    for row in read_rows(ROOT / config["recipe_aliases"]):
        aliases.setdefault(row["recipe_id"], []).append(row["alias"])
    missing = {r["id"] for r in catalog["recipes"]} - set(aliases)
    if missing:
        raise ValueError(f"recipes without aliases: {sorted(missing)}")
    categories = {row["ingredient_id"]: row["category"] for row in read_rows(ROOT / config["ingredients"])}
    vocab = Vocabulary(catalog, aliases, categories)
    family_split = split_meal_families(catalog["recipes"], config["seed"], config["recipe_split_targets"])
    recipe_split = {r["id"]: family_split[r["meal_family"]] for r in catalog["recipes"]}
    banks = {s: FamilyBank(vocab, s, [r for r, v in recipe_split.items() if v == s], config["list_families"][s],
                           config["seed"]) for s in SPLITS}
    examples, seeds = nlu_examples(vocab, banks, config)
    history = load_history(config)
    baskets, discarded = {}, {}
    for split in ("dev", "test"):
        baskets[split], discarded[split] = basket_scenarios(vocab, banks[split], split,
                                                            config["basket_targets"][split], config)
        assign_history(baskets[split], config["history_scenarios"][split], history, config, split)
    ing_groups = split_ingredients([i["id"] for i in catalog["ingredients"]], config["seed"],
                                   config["retrieval_dev_ingredients"])
    retrieval = retrieval_sets(catalog, read_rows(ROOT / config["retrieval_queries"]), ing_groups,
                               config["retrieval_counts"])

    review = []
    for split in SPLITS:
        pool = sorted((e for e in examples if e["split"] == split), key=lambda e: sha(f"{config['seed']}:review:{e['id']}"))
        review += [{"id": e["id"], "split": split, "text": e["text"], "tokens": e["tokens"], "bio_tags": e["bio_tags"],
                    "session": e["session"], "gold": e["gold"],
                    "review": {"intent_ok": None, "slots_ok": None, "gold_ok": None, "notes": ""}}
                   for e in pool[: round(len(pool) * config["review_fraction"])]]

    groups = {
        "seed": config["seed"],
        "meal_family_split": family_split,
        "recipe_split": dict(sorted(recipe_split.items())),
        "list_families": {s: banks[s].lists for s in SPLITS},
        "retrieval_ingredient_split": dict(sorted(ing_groups.items())),
    }
    nlu_split = {"grouping": "seed_id; seeds belong to meal-family and list-family groups of one split",
                 "seed_ids": seeds,
                 "example_ids": {s: [e["id"] for e in examples if e["split"] == s] for s in SPLITS}}
    checks = make_checks(examples, seeds, baskets, discarded, retrieval, groups, review, catalog, config)
    benchmark = lambda split: {"benchmark": "basket", "split": split, "policy": "docs/benchmark_policy.md",  # noqa: E731
                               "label_source": "smartcart.validation.feasibility.check_feasibility",
                               "scenarios": baskets[split]}
    texts = {
        "nlu": jsonl(examples), "review_sample": jsonl(review), "nlu_split": dump(nlu_split), "groups": dump(groups),
        "basket_dev": dump(benchmark("dev")), "basket_test": dump(benchmark("test")),
        "retrieval_dev": dump({"benchmark": "retrieval", "split": "dev", "queries": retrieval["dev"]}),
        "retrieval_test": dump({"benchmark": "retrieval", "split": "test", "queries": retrieval["test"]}),
    }
    return texts, checks


def make_checks(examples, seeds, baskets, discarded, retrieval, groups, review, catalog, config):
    by_split = Counter(e["split"] for e in examples)
    seed_sets = {s: set(v) for s, v in seeds.items()}
    families = {s: {e["family_id"] for e in examples if e["split"] == s and e["family_id"]} for s in SPLITS}
    basket_families = {s: {b["family_id"] for b in baskets[s]} for s in baskets}
    problems = Counter(p for e in examples for p in span_consistency(e))
    texts = {s: {e["text"].lower() for e in examples if e["split"] == s} for s in SPLITS}
    relabel = sum(check_feasibility(b["gold_request"], catalog)["label"] != b["label"]
                  for s in baskets for b in baskets[s])
    feature_counts = {}
    for s in baskets:
        rows = baskets[s]
        feature_counts[s] = {
            "labels": dict(Counter(b["label"] for b in rows)),
            "designs": dict(sorted(Counter(b["design"] for b in rows).items())),
            "clarification_types": dict(Counter(b["gold_request"]["clarification_type"] for b in rows
                                                if b["label"] == "clarification")),
            "infeasible_reasons": dict(Counter(b["checker"]["reason"] for b in rows if b["label"] == "infeasible")),
            "exact_budget": sum(1 for b in rows if b["label"] == "feasible"
                                and b["checker"]["min_cost_minor"] == b["gold_request"]["budget_minor"]),
            "multi_pack_lines": sum(1 for b in rows if any(l["pack_count"] > 1 for l in b["checker"].get("basket", []))),
            "pantry_covers_a_line": sum(1 for b in rows if b["checker"].get("covered_by_pantry")),
            "has_history": sum(b["has_history"] for b in rows),
            "grocery_list": sum(1 for b in rows if b["gold_request"]["intent"] == "build_grocery_list"),
            "resolved_labels": dict(Counter(b["resolved_checker"]["label"] for b in rows if b["resolved_checker"])),
            "families": len(basket_families[s]),
        }
    ing = groups["retrieval_ingredient_split"]
    retrieval_ingredients = {s: {q["required_ingredient"] for q in retrieval[s]} for s in retrieval}
    checks = {
        "nlu_examples": len(examples),
        "nlu_examples_per_split": dict(by_split),
        "nlu_seeds_per_split": {s: len(v) for s, v in seeds.items()},
        "nlu_intents_per_split": {s: dict(Counter(e["intent"] for e in examples if e["split"] == s)) for s in SPLITS},
        "nlu_clarification_types": {s: dict(Counter(e["gold"]["clarification_type"] for e in examples
                                                    if e["split"] == s and e["gold"]["needs_clarification"]))
                                    for s in SPLITS},
        "nlu_slot_label_counts": dict(Counter(sp["label"] for e in examples for sp in e["spans"])),
        "nlu_span_problems": dict(problems),
        "review_sample": {"size": len(review), "per_split": dict(Counter(r["split"] for r in review))},
        "baskets": feature_counts,
        "basket_discarded_candidates": discarded,
        "basket_labels_reproduced_by_checker": relabel == 0,
        "retrieval": {s: {"queries": len(retrieval[s]), "ingredients": len(retrieval_ingredients[s]),
                          "query_types": dict(Counter(q["query_type"] for q in retrieval[s]))} for s in retrieval},
    }
    nlu_counts = config["nlu_seeds"]
    checks["checks"] = {
        "nlu_900_examples": len(examples) == 900,
        "nlu_split_600_150_150": [by_split[s] for s in SPLITS] == [600, 150, 150],
        "no_seed_overlap": all(seed_sets[a].isdisjoint(seed_sets[b]) for a in SPLITS for b in SPLITS if a < b),
        "no_family_overlap_nlu": all(families[a].isdisjoint(families[b]) for a in SPLITS for b in SPLITS if a < b),
        "basket_test_families_not_in_dev_or_nlu_train":
            basket_families["test"].isdisjoint(basket_families["dev"] | families["train"] | families["dev"]),
        "basket_dev_families_not_in_nlu_train": basket_families["dev"].isdisjoint(families["train"]),
        "no_identical_text_across_splits": all(texts[a].isdisjoint(texts[b]) for a in SPLITS for b in SPLITS if a < b),
        "no_duplicate_paraphrase_within_seed":
            len({(e["seed_id"], e["text"].lower()) for e in examples}) == len(examples),
        "spans_consistent_with_gold": not problems,
        "basket_counts_match": all(feature_counts[s]["labels"] == config["basket_targets"][s] for s in baskets),
        "basket_labels_reproduced_by_checker": relabel == 0,
        "history_counts_match": all(feature_counts[s]["has_history"] == config["history_scenarios"][s] for s in baskets),
        "retrieval_counts_match": all(len(retrieval[s]) == n for s, n in config["retrieval_counts"].items()),
        "retrieval_ingredients_disjoint": retrieval_ingredients["dev"].isdisjoint(retrieval_ingredients["test"])
                                          and all(ing[i] == s for s in retrieval for i in retrieval_ingredients[s]),
        "review_sample_at_least_20_percent": len(review) >= 0.2 * len(examples),
        "seed_counts_match": all(len(seeds[s]) == sum(nlu_counts[s].values()) for s in SPLITS),
    }
    checks["all_checks_pass"] = all(checks["checks"].values())
    return checks


# ---------------------------------------------------------------- lock
def read_lock() -> dict[str, str]:
    if not LOCK_PATH.is_file():
        return {}
    hashes = {}
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        cells = [c.strip(" `") for c in line.split("|")]
        if len(cells) > 3 and len(cells[2]) == 64:
            hashes[cells[1]] = cells[2]
    return hashes


def write_lock(config, texts) -> None:
    rows = []
    for key in config["locked_outputs"]:
        rows.append(f"| `{config['outputs'][key]}` | `{sha(texts[key])}` | locked |")
    for key in ("basket_dev", "retrieval_dev", "review_sample"):
        rows.append(f"| `{config['outputs'][key]}` | `{sha(texts[key])}` | development (not locked) |")
    LOCK_PATH.write_text(
        "# Benchmark lock (Phase 4)\n\n"
        f"Locked on {date.today().isoformat()} by `scripts/build_benchmarks.py --lock`, after the annotation review in\n"
        "[annotation_review.md](annotation_review.md). `build_benchmarks.py --check` and\n"
        "`tests/unit/test_benchmarks.py` fail if a locked file changes. Test files are evaluated once,\n"
        "with frozen configurations (Phases 6–11). Changing a locked file requires a new lock and a\n"
        "note in `docs/progress.md` explaining why.\n\n"
        "SHA-256 of the UTF-8 file contents:\n\n"
        "| File | SHA-256 | Status |\n| --- | --- | --- |\n" + "\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/benchmarks.json"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--lock", action="store_true")
    args = parser.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    texts, checks = build_all(config)
    out = {k: ROOT / v for k, v in config["outputs"].items()}
    if args.check:
        same = {k: out[k].is_file() and out[k].read_text(encoding="utf-8") == t for k, t in texts.items()}
        lock = read_lock()
        locked = {config["outputs"][k]: lock.get(config["outputs"][k]) == sha(texts[k]) for k in config["locked_outputs"]}
        print("reproducible:", same)
        print("lock matches:", locked if lock else "no lock recorded")
        return 0 if all(same.values()) and lock and all(locked.values()) else 1
    for key, text in texts.items():
        out[key].parent.mkdir(parents=True, exist_ok=True)
        out[key].write_text(text, encoding="utf-8", newline="\n")
    out["checks"].parent.mkdir(parents=True, exist_ok=True)
    out["checks"].write_text(dump(checks), encoding="utf-8", newline="\n")
    if args.lock:
        write_lock(config, texts)
        print("lock written:", LOCK_PATH)
    print(json.dumps(checks["checks"], indent=2))
    return 0 if checks["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
