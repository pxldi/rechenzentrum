import asyncio
import os
from datetime import date, timedelta
from typing import Any

import httpx
from mcp.server import MCPServer
from pydantic import BaseModel, Field

from serve import guarded
from tandoor_mcp import leftovers as lo

mcp = MCPServer("tandoor")

# The Service name is in Tandoor's ALLOWED_HOSTS, so no Host trick is needed.
BASE_URL = os.environ.get("TANDOOR_URL", "http://tandoor.tandoor.svc.cluster.local").rstrip("/")
TOKEN = os.environ.get("TANDOOR_TOKEN", "")


def _client() -> httpx.AsyncClient:
    if not TOKEN:
        raise RuntimeError("TANDOOR_TOKEN is not set")
    return httpx.AsyncClient(
        base_url=f"{BASE_URL}/api",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        timeout=30.0,
    )


async def _get(path: str, **params: Any) -> Any:
    async with _client() as c:
        r = await c.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()


async def _get_all(path: str, **params: Any) -> list[dict]:
    """Every page of a paginated list endpoint."""
    params = {"page_size": 200, **params}
    data = await _get(path, **params)
    if not isinstance(data, dict):
        return list(data)
    items = list(data.get("results", []))
    page = 1
    while data.get("next") and page < 50:
        page += 1
        data = await _get(path, **params, page=page)
        items += data.get("results", [])
    return items


async def _send(method: str, path: str, body: dict) -> Any:
    async with _client() as c:
        r = await c.request(method, path, json=body)
        if r.status_code >= 400:
            # Tandoor's validation errors are the useful part of a failure and
            # raise_for_status would hide them.
            raise RuntimeError(f"Tandoor answered {r.status_code}: {r.text[:800]}")
        return r.json()


def _recipe_summary(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "description": (r.get("description") or "")[:300],
        "servings": r.get("servings"),
        "keywords": [k.get("name") for k in r.get("keywords") or []],
        "working_time_min": r.get("working_time"),
        "waiting_time_min": r.get("waiting_time"),
        "rating": r.get("rating"),
        "last_cooked": r.get("last_cooked"),
    }


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def search_recipes(
    query: str = Field("", description="Free text matched against recipe names, fuzzy. Empty lists everything."),
    keyword_ids: list[int] = Field(default_factory=list, description="Restrict to recipes carrying any of these keyword ids (see list_keywords)."),
    limit: int = Field(10, ge=1, le=50),
) -> list[dict]:
    """Search recipes by name and keyword. Returns id, name, servings, keywords and times, newest first."""
    params: dict[str, Any] = {"query": query or None, "page_size": limit}
    if keyword_ids:
        params["keywords_or"] = keyword_ids
    data = await _get("/recipe/", **params)
    return [_recipe_summary(r) for r in data.get("results", [])]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def get_recipe(recipe_id: int) -> dict:
    """Full recipe: description, servings, keywords, and every step with its ingredients."""
    r = await _get(f"/recipe/{recipe_id}/")
    steps = []
    for s in r.get("steps") or []:
        steps.append(
            {
                "name": s.get("name") or "",
                "instruction": s.get("instruction") or "",
                "time_min": s.get("time"),
                "ingredients": [
                    {
                        "amount": i.get("amount"),
                        "unit": (i.get("unit") or {}).get("name"),
                        "food": (i.get("food") or {}).get("name"),
                        "note": i.get("note") or "",
                    }
                    for i in s.get("ingredients") or []
                ],
            }
        )
    return {**_recipe_summary(r), "source_url": r.get("source_url"), "steps": steps}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_keywords(query: str = "") -> list[dict]:
    """Keywords (tags) with their ids, optionally filtered by a name fragment."""
    data = await _get("/keyword/", query=query or None, page_size=100)
    return [{"id": k["id"], "name": k["name"]} for k in data.get("results", [])]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_meal_types() -> list[dict]:
    """The meal types (breakfast, lunch, dinner ...) a plan entry can be filed under."""
    data = await _get("/meal-type/")
    items = data.get("results", data) if isinstance(data, dict) else data
    return [{"id": m["id"], "name": m["name"], "default_time": m.get("time")} for m in items]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_meal_plan(
    from_date: str = Field(..., description="YYYY-MM-DD, inclusive"),
    to_date: str = Field(..., description="YYYY-MM-DD, inclusive"),
) -> list[dict]:
    """Meal plan entries in a date range."""
    data = await _get("/meal-plan/", from_date=from_date, to_date=to_date)
    items = data.get("results", data) if isinstance(data, dict) else data
    out = []
    for e in items:
        recipe = e.get("recipe") or {}
        out.append(
            {
                "id": e["id"],
                "date": (e.get("from_date") or "")[:10],
                "meal_type": (e.get("meal_type") or {}).get("name"),
                "title": e.get("title") or recipe.get("name"),
                "recipe_id": recipe.get("id"),
                "servings": e.get("servings"),
                "note": e.get("note") or "",
            }
        )
    return sorted(out, key=lambda x: (x["date"], x["meal_type"] or ""))


# --- write tools -----------------------------------------------------------


class Ingredient(BaseModel):
    food: str = Field(..., description="Ingredient name, e.g. 'onion'. Created in Tandoor if new.")
    amount: float = 0
    unit: str = Field("", description="Unit name, e.g. 'g'. Empty for 'to taste'.")
    note: str = ""


class Step(BaseModel):
    instruction: str
    ingredients: list[Ingredient] = Field(default_factory=list)
    name: str = ""


def _step_payload(steps: list[Step]) -> list[dict]:
    out = []
    for s in steps:
        out.append(
            {
                "name": s.name,
                "instruction": s.instruction,
                "ingredients": [
                    {
                        "food": {"name": i.food},
                        "unit": {"name": i.unit} if i.unit else None,
                        "amount": i.amount,
                        "note": i.note,
                    }
                    for i in s.ingredients
                ],
            }
        )
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def create_recipe(
    name: str,
    steps: list[Step],
    description: str = "",
    servings: int = Field(2, ge=1),
    keywords: list[str] = Field(default_factory=list, description="Keyword names; created if new."),
    working_time_min: int = 0,
    waiting_time_min: int = 0,
    source_url: str = "",
) -> dict:
    """Create a recipe with its steps and ingredients. Returns the new recipe's id and name."""
    body = {
        "name": name,
        "description": description,
        "servings": servings,
        "working_time": working_time_min,
        "waiting_time": waiting_time_min,
        "source_url": source_url or None,
        "keywords": [{"name": k} for k in keywords],
        "steps": _step_payload(steps),
    }
    r = await _send("POST", "/recipe/", body)
    return {"id": r.get("id"), "name": r.get("name")}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def update_recipe(
    recipe_id: int,
    name: str | None = None,
    description: str | None = None,
    servings: int | None = None,
    keywords: list[str] | None = Field(None, description="Replaces the keyword list when given."),
    steps: list[Step] | None = Field(None, description="Replaces every step when given; omit to keep them."),
) -> dict:
    """Change a recipe's name, description, servings, keywords or (whole) step list. Only given fields change."""
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if servings is not None:
        body["servings"] = servings
    if keywords is not None:
        body["keywords"] = [{"name": k} for k in keywords]
    if steps is not None:
        body["steps"] = _step_payload(steps)
    if not body:
        return {"id": recipe_id, "changed": []}
    r = await _send("PATCH", f"/recipe/{recipe_id}/", body)
    return {"id": r.get("id"), "name": r.get("name"), "changed": sorted(body)}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def add_meal_plan(
    date: str = Field(..., description="YYYY-MM-DD"),
    meal_type: str = Field(..., description="Meal type name, e.g. 'Dinner' (see list_meal_types)."),
    recipe_id: int | None = Field(None, description="Recipe to plan. Omit for a free-text entry with a title."),
    title: str = Field("", description="Free-text entry, used when no recipe is given."),
    servings: int = Field(2, ge=1),
    note: str = "",
) -> dict:
    """Put a recipe (or a free-text title) on the meal plan for a date and meal type."""
    types = await list_meal_types()
    match = next((t for t in types if t["name"].lower() == meal_type.lower()), None)
    if match is None:
        raise RuntimeError(f"no meal type named {meal_type!r}; known: {[t['name'] for t in types]}")
    body: dict[str, Any] = {
        "meal_type": {"id": match["id"], "name": match["name"]},
        "from_date": date,
        "servings": servings,
        "note": note,
        "title": title,
    }
    if recipe_id is not None:
        recipe = await _get(f"/recipe/{recipe_id}/")
        body["recipe"] = {"id": recipe["id"], "name": recipe["name"]}
        body["title"] = title or recipe["name"]
    elif not title:
        raise RuntimeError("either recipe_id or title is required")
    r = await _send("POST", "/meal-plan/", body)
    return {"id": r.get("id"), "date": date, "meal_type": match["name"], "title": r.get("title")}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def log_cooked(
    recipe_id: int,
    rating: int | None = Field(None, ge=1, le=5, description="1 (never again) to 5 (loved it). Omit when not rated."),
    servings: int | None = Field(None, ge=1),
    comment: str = "",
) -> dict:
    """Record that a recipe was cooked today (a Tandoor cook log entry). leftovers()
    then treats what it needed as used up. Call again later to add a rating."""
    body: dict[str, Any] = {"recipe": recipe_id, "comment": comment}
    if rating is not None:
        body["rating"] = rating
    if servings is not None:
        body["servings"] = servings
    r = await _send("POST", "/cook-log/", body)
    return {"id": r.get("id"), "recipe_id": recipe_id, "rating": r.get("rating"), "created_at": (r.get("created_at") or "")[:10]}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def move_meal_plan(
    entry_id: int = Field(..., description="Meal plan entry id (see list_meal_plan)."),
    to_date: str = Field(..., description="New day, YYYY-MM-DD. The time of day stays as it was."),
) -> dict:
    """Move a meal plan entry to another day."""
    e = await _get(f"/meal-plan/{entry_id}/")
    old = e.get("from_date") or ""
    time_part = old[10:] if len(old) > 10 else ""
    when = f"{to_date}{time_part}"
    # The serializer's update reads servings unconditionally when the entry
    # has a shopping list attached, so it goes along with the dates.
    body = {"from_date": when, "to_date": when, "servings": e.get("servings") or 1}
    r = await _send("PATCH", f"/meal-plan/{entry_id}/", body)
    return {"id": r.get("id"), "title": r.get("title") or (r.get("recipe") or {}).get("name"), "from": old[:10], "to": to_date}


# --- leftovers -------------------------------------------------------------


async def _cooked(today: date) -> dict[int, list[date]]:
    logs, plans = await asyncio.gather(
        _get_all("/cook-log/"),
        _get("/meal-plan/", from_date=(today - timedelta(days=60)).isoformat(), to_date=today.isoformat()),
    )
    plans = plans.get("results", plans) if isinstance(plans, dict) else plans
    return lo.cooked_dates(logs, plans, today)


async def _leftovers(today: date) -> tuple[list[dict], dict[int, list[date]], int]:
    entries, conversions, cooked, prefs = await asyncio.gather(
        _get_all("/shopping-list-entry/"),
        _get_all("/unit-conversion/", query=lo.PACK_UNIT),
        _cooked(today),
        _get("/user-preference/"),
    )
    prefs = prefs[0] if isinstance(prefs, list) and prefs else prefs
    window = min(int((prefs or {}).get("shopping_recent_days") or 7), 14)
    items = lo.compute_leftovers(entries, lo.pack_sizes_from_conversions(conversions), cooked, today)
    return items, cooked, window


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def leftovers() -> dict:
    """What is probably still in the kitchen, from checked shopping list entries.

    Bought = what the recipes needed, rounded up to whole packs, plus items bought
    off-list. Cooked recipes (cook log, or a meal plan day that has passed) are
    subtracted; recipes still on the list show up as reserved_for. Each item
    decays by a shelf life from its supermarket category (produce and dairy in
    days, dry goods in months). `estimate` is true when the pack size came from a
    built-in German default rather than a UnitConversion in Tandoor; `pack.source`
    'unknown' means neither existed, ask for it and store it with set_pack_size.
    Only the last `window_days` of purchases are visible (Tandoor's shopping
    history setting, at most 14).
    """
    today = date.today()
    items, _, window = await _leftovers(today)
    return {"as_of": today.isoformat(), "window_days": window, "items": items}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def recipes_for_leftovers(
    limit: int = Field(5, ge=1, le=15),
    skip_cooked_within_days: int = Field(14, ge=0, le=90),
) -> dict:
    """Recipes ranked by how many current leftovers they use, perishables that run
    out soon weighted highest. Recipes cooked recently are skipped. `missing` lists
    the ingredients the leftovers do not cover."""
    today = date.today()
    items, cooked, _ = await _leftovers(today)
    if not items:
        return {"as_of": today.isoformat(), "leftovers": 0, "recipes": []}
    summaries = await _get_all("/recipe/")
    sem = asyncio.Semaphore(6)

    async def full(rid: int) -> dict:
        async with sem:
            return await _get(f"/recipe/{rid}/")

    recipes = await asyncio.gather(*(full(r["id"]) for r in summaries))
    ranked = lo.rank_recipes(list(recipes), items, cooked, today, skip_cooked_within_days, limit)
    return {"as_of": today.isoformat(), "leftovers": len(items), "recipes": ranked}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def set_pack_size(
    food: str = Field(..., description="Food name as it appears in Tandoor, e.g. 'Feta'."),
    amount: float = Field(..., gt=0, description="Content of one pack, e.g. 200."),
    unit: str = Field(..., description="Unit of that content: g, kg, ml or l."),
) -> dict:
    """Store how big one pack of a food is (1 Packung Feta = 200 g) as a Tandoor
    UnitConversion, so leftovers() stops estimating it. Replaces an earlier value."""
    fam, _ = lo.unit_family(unit)
    if fam not in ("mass", "volume"):
        raise RuntimeError(f"unit must be g, kg, ml or l, not {unit!r}")
    wanted = lo.normalise_food_name(food)
    foods = await _get_all("/food/", query=food)
    match = next((f for f in foods if lo.normalise_food_name(f["name"]) == wanted), None)
    if match is None:
        names = [f["name"] for f in foods[:10]]
        raise RuntimeError(f"no food named {food!r} in Tandoor; close matches: {names}")
    existing = [
        c
        for c in await _get_all("/unit-conversion/", food_id=match["id"])
        if ((c.get("base_unit") or {}).get("name") or "").lower() == lo.PACK_UNIT.lower()
    ]
    body = {
        "base_amount": 1,
        "base_unit": {"name": lo.PACK_UNIT},
        "converted_amount": amount,
        "converted_unit": {"name": unit},
        "food": {"id": match["id"], "name": match["name"]},
    }
    if existing:
        # POST would hand back the existing row unchanged (the serializer
        # dedups on food and units), so an update has to be a PATCH.
        r = await _send("PATCH", f"/unit-conversion/{existing[0]['id']}/", body)
    else:
        r = await _send("POST", "/unit-conversion/", body)
    return {"id": r.get("id"), "food": match["name"], "pack": f"1 {lo.PACK_UNIT} = {amount:g} {unit}"}
