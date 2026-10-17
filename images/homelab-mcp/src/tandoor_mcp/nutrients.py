"""Nutrient values on a Tandoor food, the way Snacky reads them.

Tandoor keeps nutrients as properties: one per property type (Kalorien,
Eiweiß, ...), each an amount for `properties_food_amount` of
`properties_food_unit`. Snacky (src/snacky/sources/tandoor.py) finds the types
by FoodData Central id first and by name second, so writes here use the same
rules and the same names when a type is missing.

A food PATCH replaces the whole property list (drf-writable-nested): listed
items with an id are updated, items without one are created, and every
property not listed is unlinked. So the existing list is always sent back.

Pure functions, so the rules are tested without Tandoor.
"""

from typing import Any

# FoodData Central nutrient ids, keyed by the tool's argument names.
FDC_IDS: dict[str, int] = {
    "kcal": 1008,
    "protein_g": 1003,
    "fat_g": 1004,
    "carbs_g": 1005,
    "fibre_g": 1079,
}

# Name and unit for a type Tandoor does not have yet; the same as Snacky's.
DEFAULT_TYPES: dict[str, tuple[str, str]] = {
    "kcal": ("Kalorien", "kcal"),
    "protein_g": ("Eiweiß", "g"),
    "fat_g": ("Fett", "g"),
    "carbs_g": ("Kohlenhydrate", "g"),
    "fibre_g": ("Ballaststoffe", "g"),
}

NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "kcal": ("kalorien", "energie", "energy", "calories", "kcal", "brennwert"),
    "protein_g": ("protein", "proteine", "proteins", "eiweiß", "eiweiss"),
    "fat_g": ("fett", "fat", "total fat", "gesamtfett", "fette"),
    "carbs_g": ("kohlenhydrate", "carbohydrate", "carbohydrates", "carbs"),
    "fibre_g": ("ballaststoffe", "ballaststoff", "fibre", "fiber", "dietary fibre", "dietary fiber"),
}

KJ_PER_KCAL = 4.184


def map_types(types: list[dict]) -> dict[str, dict]:
    """Property types keyed by nutrient. The fdc_id decides first, because
    types get renamed; names fill only what the ids left open."""
    found: dict[str, dict] = {}
    by_fdc = {v: k for k, v in FDC_IDS.items()}
    for t in types:
        key = by_fdc.get(t.get("fdc_id"))
        if key and key not in found:
            found[key] = t
    taken = {t["id"] for t in found.values()}
    for t in types:
        if t["id"] in taken:
            continue
        name = (t.get("name") or "").strip().casefold()
        for key, aliases in NAME_ALIASES.items():
            if key not in found and name in aliases:
                found[key] = t
                taken.add(t["id"])
                break
    return found


def _type_ref(t: dict) -> dict:
    # A new property is saved by a non-partial serializer, which resets the
    # nested type's order and description unless they are sent along.
    ref = {"id": t["id"], "name": t.get("name"), "unit": t.get("unit"), "fdc_id": t.get("fdc_id")}
    for k in ("order", "description"):
        if t.get(k) is not None:
            ref[k] = t[k]
    return ref


def build_properties(existing: list[dict], types: dict[str, dict], values: dict[str, float]) -> list[dict]:
    """The full property list for a PATCH: the food's other properties kept,
    the given nutrients updated or added. A kcal type kept in kJ gets kJ."""
    wanted: dict[int, float] = {}
    for key, value in values.items():
        t = types[key]
        if key == "kcal" and (t.get("unit") or "").strip().casefold() == "kj":
            value = value * KJ_PER_KCAL
        wanted[t["id"]] = round(value, 4)

    out: list[dict[str, Any]] = []
    for prop in existing:
        type_id = (prop.get("property_type") or {}).get("id")
        if type_id in wanted:
            prop = {**prop, "property_amount": wanted.pop(type_id)}
        out.append(prop)
    for t in types.values():
        if t["id"] in wanted:
            out.append({"property_amount": wanted.pop(t["id"]), "property_type": _type_ref(t)})
    return out
