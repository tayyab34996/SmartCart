"""Product text for retrieval (Phase 7).

Both retrievers index the same text for a product, so a comparison between them
isolates the model. The variants are:

- ``display_name``: the product's display name without the simulation marker, the
  house-brand words and the pack size, e.g. "SIMULATED SmartCart Basics Parmesan
  cheese (grated) 400 g" becomes "parmesan cheese grated".
- ``display_name_ingredient``: ``display_name`` plus the words of the product's
  ``ingredient_id``.
- ``display_name_aliases``: ``display_name`` plus the ingredient's reviewed aliases.
  This is a **diagnostic only**: the retrieval queries and the aliases were written by
  the same author, and 14 of the 50 dev queries are literal aliases, so the variant
  measures the alias list rather than the retriever. It is never selectable.
- ``legacy``: the Phase 1 text ``name + ingredient_id`` (lower case), kept so the E0
  baseline (Phase 5) reproduces byte for byte.
"""

from __future__ import annotations

import re

VARIANTS = ("display_name", "display_name_ingredient", "display_name_aliases", "legacy")
SELECTABLE_VARIANTS = ("display_name", "display_name_ingredient")

_SIMULATED = re.compile(r"^SIMULATED\s+")
_HOUSE_BRAND = re.compile(r"^SmartCart\s+(Basics|Select|Organic)\s+")
_PACK_SIZE = re.compile(r"\s+\d+(?:\.\d+)?\s*(?:g|ml|pieces?)$")
_SPACES = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lower case, parentheses removed, whitespace collapsed (queries and products)."""
    text = text.lower().replace("(", " ").replace(")", " ")
    return _SPACES.sub(" ", text).strip()


def display_name(product: dict) -> str:
    name = _SIMULATED.sub("", str(product["name"]).strip())
    name = _HOUSE_BRAND.sub("", name)
    name = _PACK_SIZE.sub("", name)
    return normalize_text(name)


def product_text(product: dict, variant: str, ingredients: dict | None = None) -> str:
    """Text indexed for ``product``. ``ingredients`` maps ingredient ID to its catalog
    record and is needed only for ``display_name_aliases``."""
    if variant == "legacy":
        name = str(product.get("name", ""))
        ingredient = str(product.get("ingredient_id", "")).replace("_", " ")
        return (name + " " + ingredient).strip().lower()
    base = display_name(product)
    if variant == "display_name":
        return base
    if variant == "display_name_ingredient":
        return normalize_text(base + " " + product["ingredient_id"].replace("_", " "))
    if variant == "display_name_aliases":
        if ingredients is None:
            raise ValueError("display_name_aliases needs the catalog ingredients")
        aliases = ingredients[product["ingredient_id"]].get("aliases", [])
        return normalize_text(" ".join([base, *aliases]))
    raise ValueError(f"unknown product text variant {variant}")


def catalog_texts(catalog: dict, variant: str) -> list[str]:
    """Texts for every catalog product, in catalog order."""
    ingredients = {i["id"]: i for i in catalog["ingredients"]}
    return [product_text(p, variant, ingredients) for p in catalog["products"]]
