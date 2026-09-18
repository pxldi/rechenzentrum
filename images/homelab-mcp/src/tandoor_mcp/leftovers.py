"""Work out what is left in the kitchen from Tandoor's shopping list.

The list holds what recipes need (250 g Nudeln), not what was bought
(a 500 g pack). This module turns checked entries into an estimate of what
is still in the house. It is pure: every function takes dicts as Tandoor's
API returns them and a date, so it can be tested without a token.

Model, per food and shopping trip (trip = the day the entries were checked):

    bought   = needed by recipes, rounded up to whole packs, plus anything
               bought off-list (entries with no recipe: 6 Bananen)
    consumed = needed by recipes that have been cooked since the trip
    on_hand  = bought - consumed
    reserved = needed by recipes on the list that are not cooked yet
    free     = on_hand - reserved

Every food decays by a shelf life taken from its supermarket category.
Once that has passed, the food drops out.

Tandoor only serves checked entries from the last `shopping_recent_days`
(capped at 14), so this is a two-week window at most. Dry goods therefore
fall off the estimate after two weeks even though the shelf life says
months; the tool reports the window so the model can say so.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

PACK_UNIT = "Packung"

# Mass in g, volume in ml. Anything else counts in its own unit (Stück, Bund,
# Dose, EL), where one pack is one of that unit.
_MASS = {"g": 1.0, "kg": 1000.0}
_VOLUME = {"ml": 1.0, "l": 1000.0, "liter": 1000.0}

# Shelf life in days by Tandoor open-data category slug, with the German
# category names of this instance as a fallback where the slug is unset.
SHELF_LIFE_DAYS = {
    "category-produce": 7,
    "category-bakery": 4,
    "category-meat": 3,
    "category-fish": 2,
    "category-dairy": 10,
    "category-cheese": 14,
    "category-deli": 10,
    "category-frozen": 90,
}
_SHELF_LIFE_BY_NAME = {
    "obst & gemüse": 7,
    "brot & backwaren": 4,
    "fleisch": 3,
    "fisch": 2,
    "kühlregal": 10,
    "käse": 14,
    "feinkost & tofu": 10,
    "tiefkühl": 90,
}
# Foods whose name says more than their category (fresh herbs and leaves
# are produce but last days, not a week).
_SHELF_LIFE_BY_FOOD = {
    "petersilie": 4,
    "koriander": 4,
    "basilikum": 4,
    "dill": 4,
    "schnittlauch": 4,
    "feldsalat": 3,
    "rucola": 3,
    "salat": 4,
    "spinat": 4,
    "bananen": 5,
    "banane": 5,
    "brot": 4,
    "brötchen": 2,
}
DEFAULT_SHELF_LIFE_DAYS = 180
PERISHABLE_MAX_DAYS = 14

# The usual German supermarket pack, by a lowercase fragment of the food
# name. Longer fragments win, so "räuchertofu" beats "tofu". These are
# estimates; a UnitConversion in Tandoor (set_pack_size) overrides them.
DEFAULT_PACKS: dict[str, tuple[float, str]] = {
    "nudel": (500, "g"),
    "spaghetti": (500, "g"),
    "penne": (500, "g"),
    "fusilli": (500, "g"),
    "tagliatelle": (500, "g"),
    "pasta": (500, "g"),
    "lasagneplatten": (250, "g"),
    "spätzle": (500, "g"),
    "reis": (500, "g"),
    "risottoreis": (500, "g"),
    "couscous": (500, "g"),
    "bulgur": (500, "g"),
    "quinoa": (500, "g"),
    "haferflocken": (500, "g"),
    "rote linsen": (500, "g"),
    "linsen": (500, "g"),
    "kichererbsen": (240, "g"),
    "kidneybohnen": (240, "g"),
    "bohnen": (240, "g"),
    "mais": (285, "g"),
    "feta": (200, "g"),
    "tofu": (200, "g"),
    "räuchertofu": (200, "g"),
    "sojaschnetzel": (200, "g"),
    "sahne": (200, "ml"),
    "hafersahne": (200, "ml"),
    "sojasahne": (200, "ml"),
    "kochcreme": (200, "ml"),
    "kokosmilch": (400, "ml"),
    "kokosnussmilch": (400, "ml"),
    "milch": (1000, "ml"),
    "hafermilch": (1000, "ml"),
    "haferdrink": (1000, "ml"),
    "sojamilch": (1000, "ml"),
    "joghurt": (500, "g"),
    "frischkäse": (200, "g"),
    "schmand": (200, "g"),
    "crème fraîche": (200, "g"),
    "butter": (250, "g"),
    "margarine": (250, "g"),
    "parmesan": (100, "g"),
    "passierte tomaten": (500, "g"),
    "gehackte tomaten": (400, "g"),
    "stückige tomaten": (400, "g"),
    "tomatenmark": (200, "g"),
    "mehl": (1000, "g"),
    "zucker": (1000, "g"),
    "hefe": (1, "Stück"),
    "blätterteig": (275, "g"),
    "pizzateig": (400, "g"),
    "spinat (tk)": (450, "g"),
    "tk-spinat": (450, "g"),
    "erdnussbutter": (350, "g"),
    "erdnussmus": (250, "g"),
    "tahini": (250, "g"),
    "hummus": (200, "g"),
    "miso": (300, "g"),
    "sojasauce": (150, "ml"),
    "sojasoße": (150, "ml"),
    "currypaste": (100, "g"),
    "kokosöl": (200, "ml"),
    "olivenöl": (500, "ml"),
    "walnüsse": (200, "g"),
    "cashew": (200, "g"),
    "kürbiskerne": (100, "g"),
    "sesam": (100, "g"),
    "chiasamen": (250, "g"),
    "champignons": (250, "g"),
    "pilze": (250, "g"),
    "feldsalat": (100, "g"),
    "rucola": (100, "g"),
    "babyspinat": (125, "g"),
}


def unit_family(unit: str | None) -> tuple[str, float]:
    """('mass', factor to g) / ('volume', factor to ml) / (the unit's own
    lowercase name, 1). No unit means pieces."""
    name = (unit or "").strip().lower()
    if not name:
        return ("stück", 1.0)
    if name in _MASS:
        return ("mass", _MASS[name])
    if name in _VOLUME:
        return ("volume", _VOLUME[name])
    return (name, 1.0)


def family_unit(family: str) -> str:
    return {"mass": "g", "volume": "ml"}.get(family, family)


def shelf_life_days(food: dict) -> int:
    name = (food.get("name") or "").lower()
    for fragment, days in _SHELF_LIFE_BY_FOOD.items():
        if fragment in name:
            return days
    cat = food.get("supermarket_category") or {}
    slug = cat.get("open_data_slug") or ""
    if slug in SHELF_LIFE_DAYS:
        return SHELF_LIFE_DAYS[slug]
    return _SHELF_LIFE_BY_NAME.get((cat.get("name") or "").lower(), DEFAULT_SHELF_LIFE_DAYS)


def default_pack(food_name: str) -> tuple[float, str] | None:
    name = food_name.lower()
    hits = [k for k in DEFAULT_PACKS if k in name]
    if not hits:
        return None
    return DEFAULT_PACKS[max(hits, key=len)]


def pack_sizes_from_conversions(conversions: list[dict]) -> dict[int, tuple[float, str]]:
    """food id -> (amount, unit) from Tandoor UnitConversions that mention a
    pack on either side (1 Packung Nudeln = 500 g, or the reverse)."""
    out: dict[int, tuple[float, str]] = {}
    for c in conversions:
        food = c.get("food") or {}
        if not food.get("id"):
            continue
        bu = ((c.get("base_unit") or {}).get("name") or "").lower()
        cu = ((c.get("converted_unit") or {}).get("name") or "").lower()
        ba, ca = float(c.get("base_amount") or 0), float(c.get("converted_amount") or 0)
        if bu == PACK_UNIT.lower() and ba > 0 and ca > 0:
            out[food["id"]] = (ca / ba, (c.get("converted_unit") or {}).get("name"))
        elif cu == PACK_UNIT.lower() and ba > 0 and ca > 0:
            out[food["id"]] = (ba / ca, (c.get("base_unit") or {}).get("name"))
    return out


def resolve_pack(food: dict, family: str, known: dict[int, tuple[float, str]]) -> tuple[float | None, str]:
    """Pack size in the entry's unit family, and where it came from:
    'tandoor', 'default', 'unit' (one of a counted unit) or 'unknown'."""
    if family not in ("mass", "volume"):
        return (1.0, "unit")
    src = "tandoor"
    pack = known.get(food.get("id"))
    if pack is None:
        pack = default_pack(food.get("name") or "")
        src = "default"
    if pack is None:
        return (None, "unknown")
    amount, unit = pack
    fam, factor = unit_family(unit)
    if fam != family:
        return (None, "unknown")
    return (amount * factor, src)


def _day(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def cooked_dates(cook_logs: list[dict], meal_plans: list[dict], today: date) -> dict[int, list[date]]:
    """recipe id -> days it counts as cooked: every CookLog, and every meal
    plan whose day has passed (a planned day that went by counts as cooked
    unless the person said otherwise)."""
    out: dict[int, list[date]] = {}
    for log in cook_logs:
        rid = log.get("recipe") if not isinstance(log.get("recipe"), dict) else log["recipe"].get("id")
        d = _day(log.get("created_at"))
        if rid and d:
            out.setdefault(int(rid), []).append(d)
    for mp in meal_plans:
        rid = (mp.get("recipe") or {}).get("id")
        d = _day(mp.get("from_date"))
        if rid and d and d <= today:
            out.setdefault(int(rid), []).append(d)
    return out


def _round(x: float) -> float:
    return round(x + 1e-9, 2)


def compute_leftovers(
    entries: list[dict],
    known_packs: dict[int, tuple[float, str]],
    cooked: dict[int, list[date]],
    today: date,
) -> list[dict]:
    """See the module docstring. `entries` are shopping list entries as the
    API returns them; unchecked ones are ignored."""
    trips: dict[tuple[int, date], dict] = {}
    for e in entries:
        if not e.get("checked"):
            continue
        food = e.get("food") or {}
        bought_on = _day(e.get("completed_at"))
        if not food.get("id") or bought_on is None:
            continue
        unit_name = (e.get("unit") or {}).get("name")
        family, factor = unit_family(unit_name)
        amount = float(e.get("amount") or 0) * factor
        lr = e.get("list_recipe_data") or {}
        recipe = lr.get("recipe_data") or {}
        trip = trips.setdefault(
            (food["id"], bought_on),
            {"food": food, "bought_on": bought_on, "families": {}},
        )
        fam = trip["families"].setdefault(
            family,
            {"needed": 0.0, "consumed": 0.0, "off_list": 0.0, "reserved_for": {}, "cooked": [], "unit": unit_name or "Stück"},
        )
        if recipe.get("id"):
            fam["needed"] += amount
            done = any(d >= bought_on for d in cooked.get(int(recipe["id"]), []))
            if done:
                fam["consumed"] += amount
                fam["cooked"].append(recipe.get("name"))
            else:
                fam["reserved_for"][int(recipe["id"])] = recipe.get("name")
        else:
            fam["off_list"] += amount

    per_food: dict[int, dict] = {}
    for (food_id, bought_on), trip in sorted(trips.items(), key=lambda kv: kv[0][1]):
        food = trip["food"]
        shelf = shelf_life_days(food)
        age = (today - bought_on).days
        remaining = shelf - age
        if remaining <= 0:
            continue
        for family, fam in trip["families"].items():
            pack, source = resolve_pack(food, family, known_packs)
            unit = family_unit(family) if family in ("mass", "volume") else fam["unit"]
            if pack is None:
                on_hand = free = None
                bought = None
            else:
                packs = math.ceil(fam["needed"] / pack - 1e-9) if fam["needed"] > 0 else 0
                bought = packs * pack + fam["off_list"]
                on_hand = bought - fam["consumed"]
                free = on_hand - (fam["needed"] - fam["consumed"])
            item = per_food.setdefault(
                (food_id, family),
                {
                    "food_id": food_id,
                    "food": food.get("name"),
                    "category": (food.get("supermarket_category") or {}).get("name"),
                    "unit": unit,
                    "on_hand": 0.0,
                    "free": 0.0,
                    "reserved_for": [],
                    "reserved_for_ids": [],
                    "bought_on": bought_on.isoformat(),
                    "expires_in_days": remaining,
                    "shelf_life_days": shelf,
                    "pack": {"amount": pack, "unit": unit, "source": source},
                    "estimate": source in ("default", "unknown"),
                    "needed": 0.0,
                },
            )
            item["needed"] += fam["needed"] + fam["off_list"]
            for rid, rname in fam["reserved_for"].items():
                if rid not in item["reserved_for_ids"]:
                    item["reserved_for_ids"].append(rid)
                    item["reserved_for"].append(rname)
            item["expires_in_days"] = min(item["expires_in_days"], remaining)
            if on_hand is None or item["on_hand"] is None:
                item["on_hand"] = item["free"] = None
            else:
                item["on_hand"] += on_hand
                item["free"] += free

    out = []
    for item in per_food.values():
        if item["on_hand"] is not None:
            item["on_hand"] = _round(item["on_hand"])
            item["free"] = _round(max(item["free"], 0.0))
            if item["on_hand"] <= 0:
                continue
        item["needed"] = _round(item["needed"])
        item["perishable"] = item["shelf_life_days"] <= PERISHABLE_MAX_DAYS
        out.append(item)
    out.sort(key=lambda i: (i["expires_in_days"], i["food"] or ""))
    return out


def _urgency(item: dict) -> float:
    shelf = max(item.get("shelf_life_days") or 1, 1)
    return 1.0 - min(item.get("expires_in_days") or 0, shelf) / shelf


def rank_recipes(
    recipes: list[dict],
    leftovers: list[dict],
    cooked: dict[int, list[date]],
    today: date,
    skip_cooked_within_days: int = 14,
    limit: int = 5,
) -> list[dict]:
    """Rank full recipes (with steps and ingredients) by the leftovers they
    use. A perishable that runs out soon weighs up to three times a dry
    good. Recipes cooked within `skip_cooked_within_days` are left out.
    Food reserved for a recipe still on the list counts for that recipe."""
    by_food: dict[int, dict] = {}
    for item in leftovers:
        by_food[item["food_id"]] = item

    def usable(item: dict, rid: int) -> bool:
        if item.get("on_hand") is None:
            return True
        return (item.get("free") or 0) > 0 or rid in item.get("reserved_for_ids", [])
    ranked = []
    for r in recipes:
        rid = r.get("id")
        recent = [d for d in cooked.get(int(rid), []) if (today - d).days <= skip_cooked_within_days]
        if recent:
            continue
        seen: set[int] = set()
        used, missing = [], []
        score = 0.0
        for step in r.get("steps") or []:
            for ing in step.get("ingredients") or []:
                food = ing.get("food") or {}
                fid = food.get("id")
                if not fid or fid in seen:
                    continue
                seen.add(fid)
                item = by_food.get(fid)
                if item is not None and usable(item, int(rid)):
                    weight = 1.0 + (2.0 * _urgency(item) if item.get("perishable") else 0.0)
                    score += weight
                    used.append(item["food"])
                else:
                    missing.append(food.get("name"))
        if not used:
            continue
        ranked.append(
            {
                "recipe_id": rid,
                "name": r.get("name"),
                "servings": r.get("servings"),
                "score": _round(score),
                "uses": used,
                "missing": missing,
                "keywords": [k.get("name") or k.get("label") for k in r.get("keywords") or []],
            }
        )
    ranked.sort(key=lambda x: (-x["score"], len(x["missing"]), x["name"] or ""))
    return ranked[:limit]


def normalise_food_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())
