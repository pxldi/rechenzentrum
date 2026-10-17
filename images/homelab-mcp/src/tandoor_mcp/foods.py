"""Matching a food name against the foods Tandoor already has.

Tandoor creates a new food for every name it has not seen, so "Zwiebel, klein"
next to "Zwiebel" becomes a second food with its own shopping category and
pack size. Before a write creates one, the server looks for the existing food:

- the same name up to case, spacing and a plural ending is the same food and
  is used silently ("Zwiebeln" for "Zwiebel");
- a name that shares its first part ("Zwiebel, klein", "Ingwer (frisch)") or
  reads much alike is probably the same food, but not always ("Tomaten,
  passiert" is not "Tomaten"), so the caller is asked to choose;
- anything else is new.

Pure functions, so the rules are tested without Tandoor.
"""

import re
from difflib import SequenceMatcher

from tandoor_mcp.leftovers import normalise_food_name

# Above this a name is the same food spelled differently (plural, a typo).
SAME = 0.9
# Above this, or with the same first part, it is worth asking about.
SIMILAR = 0.75


def base_name(name: str) -> str:
    """The part before a comma or parenthesis: 'Zwiebel, klein' -> 'zwiebel'."""
    return re.split(r"[,(]", normalise_food_name(name), maxsplit=1)[0].strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalise_food_name(a), normalise_food_name(b)).ratio()


def match_food(name: str, candidates: list[dict]) -> tuple[dict | None, list[dict]]:
    """(the food to use, similar foods to ask about).

    The first is set when one candidate is the same food; then the list is
    empty. Otherwise the list holds the plausible matches, best first, and an
    empty list means the name is new."""
    wanted = normalise_food_name(name)
    if not wanted:
        return None, []
    scored = []
    for c in candidates:
        cname = c.get("name") or ""
        if normalise_food_name(cname) == wanted:
            return c, []
        scored.append((similarity(name, cname), c))
    scored.sort(key=lambda t: -t[0])
    wanted_base = base_name(name)
    if scored and scored[0][0] >= SAME:
        best = scored[0][1]
        # A qualifier is part of the food: "Tomaten, passiert" may read like
        # "Tomaten, passierte" but not like "Tomaten", so a near spelling only
        # counts when both have the same first part or neither has a qualifier.
        best_name = normalise_food_name(best.get("name") or "")
        unqualified = not re.search(r"[,(]", wanted) and not re.search(r"[,(]", best_name)
        if unqualified or base_name(best_name) == wanted_base:
            return best, []
    similar = [c for s, c in scored if s >= SIMILAR or (wanted_base and base_name(c.get("name") or "") == wanted_base)]
    return None, similar[:5]
