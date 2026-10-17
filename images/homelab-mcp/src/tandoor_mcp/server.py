import asyncio
import os
from datetime import date, timedelta
from typing import Any

import httpx
from mcp.server import MCPServer
from pydantic import BaseModel, Field

from oauth import server_kwargs
from serve import guarded
from tandoor_mcp import foods as fm
from tandoor_mcp import leftovers as lo

mcp = MCPServer("tandoor", **server_kwargs())

# The Service name is in Tandoor's ALLOWED_HOSTS, so no Host trick is needed.
BASE_URL = os.environ.get("TANDOOR_URL", "http://tandoor.tandoor.svc.cluster.local").rstrip("/")
TOKEN = os.environ.get("TANDOOR_TOKEN", "")
# The most items one batch tool takes per call.
MAX_BATCH = 50


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
        # The list endpoint's keywords carry `label`, the detail endpoint's `name`.
        "keywords": [k.get("name") or k.get("label") for k in r.get("keywords") or []],
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
    keywords: list[str] = Field(default_factory=list, description="Keyword names, matched case-insensitively; the same as keyword_ids without the lookup."),
    match_all_keywords: bool = Field(False, description="Require every given keyword instead of any of them."),
    limit: int = Field(10, ge=1, le=50),
) -> list[dict]:
    """Search recipes by name and keyword. Returns id, name, servings, keywords and
    times, so a question like 'schnelle Meal-Prep-Gerichte' needs no get_recipe per hit."""
    params: dict[str, Any] = {"query": query or None, "page_size": limit}
    ids = list(keyword_ids)
    if keywords:
        known = {k["name"].lower(): k["id"] for k in await _get_all("/keyword/")}
        unknown = [k for k in keywords if k.lower() not in known]
        if unknown:
            raise RuntimeError(f"no keyword named {unknown}; see list_keywords")
        ids += [known[k.lower()] for k in keywords]
    if ids:
        params["keywords_and" if match_all_keywords else "keywords_or"] = ids
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


class PlanEntry(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    meal_type: str = Field(..., description="Meal type name, e.g. 'Dinner' (see list_meal_types).")
    recipe_id: int | None = Field(None, description="Recipe to plan. Omit for a free-text entry with a title.")
    title: str = Field("", description="Free-text entry, used when no recipe is given.")
    servings: int = Field(2, ge=1)
    note: str = ""
    add_to_shopping_list: bool = Field(False, description="Also put the recipe's ingredients on the shopping list, linked to this entry.")


async def _add_plan(e: PlanEntry, types: list[dict]) -> dict:
    match = next((t for t in types if t["name"].lower() == e.meal_type.lower()), None)
    if match is None:
        raise RuntimeError(f"no meal type named {e.meal_type!r}; known: {[t['name'] for t in types]}")
    body: dict[str, Any] = {
        "meal_type": {"id": match["id"], "name": match["name"]},
        "from_date": e.date,
        "servings": e.servings,
        "note": e.note,
        "title": e.title,
        "addshopping": bool(e.add_to_shopping_list and e.recipe_id is not None),
    }
    if e.recipe_id is not None:
        recipe = await _get(f"/recipe/{e.recipe_id}/")
        body["recipe"] = {"id": recipe["id"], "name": recipe["name"]}
        body["title"] = e.title or recipe["name"]
    elif not e.title:
        raise RuntimeError("either recipe_id or title is required")
    r = await _send("POST", "/meal-plan/", body)
    return {"id": r.get("id"), "date": e.date, "meal_type": match["name"], "title": r.get("title"), "on_shopping_list": bool(r.get("shopping"))}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def add_meal_plan(
    date: str = Field(..., description="YYYY-MM-DD"),
    meal_type: str = Field(..., description="Meal type name, e.g. 'Dinner' (see list_meal_types)."),
    recipe_id: int | None = Field(None, description="Recipe to plan. Omit for a free-text entry with a title."),
    title: str = Field("", description="Free-text entry, used when no recipe is given."),
    servings: int = Field(2, ge=1),
    note: str = "",
    add_to_shopping_list: bool = Field(False, description="Also put the recipe's ingredients on the shopping list, linked to this entry."),
) -> dict:
    """Put a recipe (or a free-text title) on the meal plan for a date and meal type.
    With add_to_shopping_list the ingredients land on the shopping list too."""
    entry = PlanEntry(
        date=date, meal_type=meal_type, recipe_id=recipe_id, title=title,
        servings=servings, note=note, add_to_shopping_list=add_to_shopping_list,
    )
    return await _add_plan(entry, await list_meal_types())


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def add_meal_plans(entries: list[PlanEntry] = Field(..., min_length=1, max_length=MAX_BATCH)) -> list[dict]:
    """Plan several meals at once, e.g. a whole week. One result per entry, in
    order: the new entry, or `error` for one that failed; the others still land."""
    types = await list_meal_types()
    out = []
    for e in entries:
        try:
            out.append({**await _add_plan(e, types), "added": True})
        except (httpx.HTTPError, RuntimeError) as err:
            out.append({"date": e.date, "meal_type": e.meal_type, "added": False, "error": str(err)[:300]})
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def log_cooked(
    recipe_id: int,
    rating: int | None = Field(None, ge=1, le=5, description="1 (never again) to 5 (loved it). Omit when not rated."),
    servings: int | None = Field(None, ge=1),
    comment: str = "",
    cooked_on: str | None = Field(None, description="YYYY-MM-DD when it was not today, e.g. 'das hab ich Dienstag gekocht'."),
) -> dict:
    """Record that a recipe was cooked (a Tandoor cook log entry), today or on
    cooked_on. leftovers() then treats what it needed as used up. Call again
    later to add a rating."""
    body: dict[str, Any] = {"recipe": recipe_id, "comment": comment}
    if cooked_on:
        body["created_at"] = f"{cooked_on}T19:00:00"
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


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def delete_meal_plan(entry_id: int = Field(..., description="Meal plan entry id (see list_meal_plan).")) -> dict:
    """Delete a meal plan entry. Shopping list items that add_meal_plan put on the
    list for this entry go with it; the recipe itself stays."""
    e = await _get(f"/meal-plan/{entry_id}/")
    async with _client() as c:
        r = await c.delete(f"/meal-plan/{entry_id}/")
        if r.status_code >= 400:
            raise RuntimeError(f"Tandoor answered {r.status_code}: {r.text[:300]}")
    return {
        "deleted": entry_id,
        "date": (e.get("from_date") or "")[:10],
        "title": e.get("title") or (e.get("recipe") or {}).get("name"),
    }


# --- recipe import ---------------------------------------------------------


async def _scrape(url: str) -> dict:
    r = await _send("POST", "/recipe-from-source/", {"url": url, "data": ""})
    if r.get("error") or not r.get("recipe"):
        raise RuntimeError(f"Tandoor could not read that page: {r.get('msg') or 'no recipe found'}")
    return r


def _scraped_summary(rec: dict) -> dict:
    ingredients = [
        f"{i.get('amount') or ''} {(i.get('unit') or {}).get('name') or ''} {(i.get('food') or {}).get('name') or ''}".strip()
        for st in rec.get("steps") or []
        for i in st.get("ingredients") or []
    ]
    return {
        "name": rec.get("name"),
        "servings": rec.get("servings"),
        "working_time_min": rec.get("working_time"),
        "waiting_time_min": rec.get("waiting_time"),
        "steps": len(rec.get("steps") or []),
        "ingredients": ingredients,
        "keywords": [k.get("name") for k in rec.get("keywords") or []][:12],
        "has_image": bool(rec.get("image_url")),
    }


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def preview_recipe_from_url(url: str = Field(..., description="A recipe page, e.g. from Chefkoch or BBC Good Food.")) -> dict:
    """Read a recipe page with Tandoor's scraper and show what would be imported. Nothing is saved."""
    r = await _scrape(url)
    out = _scraped_summary(r["recipe"])
    out["already_imported"] = [{"id": d.get("id"), "name": d.get("name")} for d in r.get("duplicates") or []]
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def import_recipe_from_url(
    url: str = Field(..., description="A recipe page. Use preview_recipe_from_url first and show the person the summary."),
    keywords: list[str] = Field(default_factory=list, description="Keywords for the recipe, e.g. ['vegan', 'wochentag']. The page's own tags are not imported."),
) -> dict:
    """Scrape a recipe page and save it as a Tandoor recipe, with its image when the page has one."""
    r = await _scrape(url)
    rec = r["recipe"]
    # Pages bring 20 tags of their own ("Autumn", "Dinner party", ...), which
    # would swamp the keyword list; only what the person asked for is kept.
    keyword_objs = [{"name": k} for k in keywords if k]
    # The scraper leaves every order field null and the serializer rejects
    # that, so number the steps and ingredients here.
    steps = []
    for si, st in enumerate(rec.get("steps") or []):
        ingredients = [{**i, "order": ii} for ii, i in enumerate(st.get("ingredients") or [])]
        steps.append({**st, "order": si, "ingredients": ingredients})
    body = {
        "name": rec.get("name"),
        "description": rec.get("description") or "",
        "servings": rec.get("servings") or 2,
        "servings_text": rec.get("servings_text") or "",
        "working_time": rec.get("working_time") or 0,
        "waiting_time": rec.get("waiting_time") or 0,
        "source_url": rec.get("source_url") or url,
        "internal": True,
        "keywords": keyword_objs,
        "steps": steps,
    }
    created = await _send("POST", "/recipe/", body)
    image = False
    if rec.get("image_url"):
        try:
            await _send("PUT", f"/recipe/{created['id']}/image/", {"image_url": rec["image_url"]})
            image = True
        except RuntimeError:
            image = False
    return {"id": created.get("id"), "name": created.get("name"), "image": image, **_scraped_summary(rec)}


# --- shopping list ---------------------------------------------------------


def _entry_summary(e: dict) -> dict:
    lr = e.get("list_recipe_data") or {}
    return {
        "id": e["id"],
        "food": (e.get("food") or {}).get("name"),
        "amount": e.get("amount"),
        "unit": (e.get("unit") or {}).get("name"),
        "checked": bool(e.get("checked")),
        "recipe": ((lr.get("recipe_data") or {}).get("name")) if lr else None,
        "recipe_id": lr.get("recipe") if lr else None,
        "meal_plan_id": lr.get("mealplan") if lr else None,
    }


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_shopping_list(include_checked: bool = Field(False, description="Also return recently checked entries.")) -> list[dict]:
    """The shopping list: open entries with id, food, amount, unit and the recipe they came from."""
    entries = await _get_all("/shopping-list-entry/")
    return [_entry_summary(e) for e in entries if include_checked or not e.get("checked")]


class ShoppingItem(BaseModel):
    food: str = Field(..., description="Food name. An existing food is used when the name matches one (case, spacing, plural).")
    amount: float = Field(1, ge=0)
    unit: str = Field("", description="Unit name, e.g. 'g'. Empty for pieces.")
    new_food: bool = Field(False, description="Create the food even though similar ones exist. Only after the person said it is a different food.")


async def _food_candidates(name: str) -> list[dict]:
    """Foods that may be `name`: what Tandoor's search returns for the whole name
    and for its first part, so 'Zwiebel, klein' also finds 'Zwiebel'."""
    queries = {name.strip(), fm.base_name(name)}
    results = await asyncio.gather(*(_get("/food/", query=q, page_size=25) for q in queries if q))
    seen: dict[int, dict] = {}
    for data in results:
        for f in data.get("results", []) if isinstance(data, dict) else data:
            seen.setdefault(f["id"], f)
    return list(seen.values())


def _food_summary(f: dict) -> dict:
    return {
        "id": f["id"],
        "name": f.get("name"),
        "on_hand": bool(f.get("food_onhand")),
        "never_on_shopping_list": bool(f.get("ignore_shopping")),
        "category": (f.get("supermarket_category") or {}).get("name"),
        "on_shopping_list": str(f.get("shopping")).lower() == "true",
        "used_in_recipes": f.get("numrecipe"),
    }


async def _resolve_food(name: str, new_food: bool = False) -> tuple[dict | None, list[dict]]:
    """(food payload for a write, similar foods when the caller has to choose)."""
    match, similar = fm.match_food(name, await _food_candidates(name))
    if match is not None:
        return {"id": match["id"], "name": match["name"]}, []
    if similar and not new_food:
        return None, [{"id": f["id"], "name": f["name"]} for f in similar]
    return {"name": name.strip()}, []


async def _add_item(item: ShoppingItem) -> dict:
    food, similar = await _resolve_food(item.food, item.new_food)
    if food is None:
        return {
            "food": item.food,
            "added": False,
            "similar_foods": similar,
            "hint": "Not added: Tandoor has similar foods. Retry with one of their names, or with new_food=true if it really is a different food.",
        }
    body: dict[str, Any] = {"food": food, "amount": item.amount, "unit": {"name": item.unit} if item.unit else None}
    r = await _send("POST", "/shopping-list-entry/", body)
    out = {**_entry_summary(r), "added": True}
    if "id" in food and fm.normalise_food_name(food["name"]) != fm.normalise_food_name(item.food):
        out["used_existing_food"] = food["name"]
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def add_shopping_items(items: list[ShoppingItem] = Field(..., min_length=1, max_length=MAX_BATCH)) -> list[dict]:
    """Put several items on the shopping list in one call. Each name is matched
    against the foods Tandoor has; a name that only resembles existing foods
    ('Zwiebel, klein' when 'Zwiebel' exists) is not added and comes back with
    similar_foods to choose from."""
    # One after the other: two items naming the same new food would otherwise
    # race and create it twice. A failing item does not stop the rest.
    out = []
    for i in items:
        try:
            out.append(await _add_item(i))
        except (httpx.HTTPError, RuntimeError) as e:
            out.append({"food": i.food, "added": False, "error": str(e)[:300]})
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def add_shopping_item(
    food: str = Field(..., description="Food name. An existing food is used when the name matches one."),
    amount: float = Field(1, ge=0),
    unit: str = Field("", description="Unit name, e.g. 'g'. Empty for pieces."),
    new_food: bool = Field(False, description="Create the food even though similar ones exist."),
) -> dict:
    """Put one item on the shopping list. Same matching as add_shopping_items."""
    return await _add_item(ShoppingItem(food=food, amount=amount, unit=unit, new_food=new_food))


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def update_shopping_item(
    entry_id: int = Field(..., description="Entry id from list_shopping_list."),
    amount: float | None = Field(None, ge=0),
    unit: str | None = Field(None, description="New unit name; empty string for pieces."),
) -> dict:
    """Change the amount or unit of a shopping list entry."""
    body: dict[str, Any] = {}
    if amount is not None:
        body["amount"] = amount
    if unit is not None:
        body["unit"] = {"name": unit} if unit else None
    if not body:
        raise RuntimeError("give amount, unit or both")
    return _entry_summary(await _send("PATCH", f"/shopping-list-entry/{entry_id}/", body))


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def check_shopping_items(
    entry_ids: list[int] = Field(..., min_length=1, max_length=MAX_BATCH, description="Entry ids from list_shopping_list."),
    checked: bool = Field(True, description="False takes the tick off again."),
) -> list[dict]:
    """Tick entries off as bought. They stay in the list's history (and count for
    leftovers()), unlike remove_shopping_items. One result per id: checked
    (or unchecked), or not_found."""
    async def exists(i: int) -> bool:
        async with _client() as c:
            r = await c.get(f"/shopping-list-entry/{i}/")
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True

    found = await asyncio.gather(*(exists(i) for i in entry_ids))
    ids = [i for i, ok in zip(entry_ids, found) if ok]
    if ids:
        await _send("POST", "/shopping-list-entry/bulk/", {"ids": ids, "checked": checked})
    state = "checked" if checked else "unchecked"
    return [{"id": i, "status": state if ok else "not_found"} for i, ok in zip(entry_ids, found)]


async def _delete_entry(entry_id: int) -> dict:
    """One entry's outcome. An id that is already gone is not an error, so a
    repeated call is harmless."""
    try:
        async with _client() as c:
            r = await c.delete(f"/shopping-list-entry/{entry_id}/")
    except httpx.HTTPError as e:
        return {"id": entry_id, "status": "error", "error": str(e)[:200]}
    if r.status_code == 404:
        return {"id": entry_id, "status": "already_removed"}
    if r.status_code >= 400:
        return {"id": entry_id, "status": "error", "error": f"Tandoor answered {r.status_code}: {r.text[:200]}"}
    return {"id": entry_id, "status": "removed"}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def remove_shopping_items(
    entry_ids: list[int] = Field(..., min_length=1, max_length=MAX_BATCH, description="Entry ids from list_shopping_list."),
) -> list[dict]:
    """Take entries off the shopping list (deleted, not ticked): what is already at
    home after a recipe went on the list, or duplicates. For bought items use
    check_shopping_items. One result per id: removed, already_removed or error."""
    return list(await asyncio.gather(*(_delete_entry(i) for i in entry_ids)))


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def remove_shopping_item(entry_id: int = Field(..., description="Entry id from list_shopping_list.")) -> dict:
    """Take one entry off the shopping list (deleted, not ticked). Use it to drop what
    is already in the house after add_meal_plan put a whole recipe on the list."""
    result = await _delete_entry(entry_id)
    if result["status"] == "error":
        raise RuntimeError(result["error"])
    return {"removed": entry_id, "status": result["status"]}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def add_recipe_to_shopping_list(
    recipe_id: int,
    servings: int = Field(..., ge=1, description="Portions to shop for; amounts scale from the recipe's own servings."),
) -> dict:
    """Put a recipe's ingredients on the shopping list without planning it ('Chili
    für 4 Portionen auf die Liste'). Foods marked never_on_shopping_list are left
    out, and so are on-hand foods when Tandoor's 'exclude on hand' setting is on."""
    recipe = await _get(f"/recipe/{recipe_id}/")
    await _send("PUT", f"/recipe/{recipe_id}/shopping/", {"servings": servings})
    entries = await _get_all("/shopping-list-entry/")
    added = [
        _entry_summary(e)
        for e in entries
        if not e.get("checked")
        and (e.get("list_recipe_data") or {}).get("recipe") == recipe_id
        and not (e.get("list_recipe_data") or {}).get("mealplan")
    ]
    return {"recipe": recipe.get("name"), "servings": servings, "entries": added}


# --- foods -----------------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def search_food(query: str = Field(..., description="Food name or part of it."), limit: int = Field(10, ge=1, le=50)) -> list[dict]:
    """Foods Tandoor knows that match a name, with whether each is on hand, never
    goes on the shopping list, is on it now, and how many recipes use it. Use it
    before naming a food in a write, and to find duplicates for merge_food."""
    candidates = await _food_candidates(query)
    candidates.sort(key=lambda f: -fm.similarity(query, f.get("name") or ""))
    return [_food_summary(f) for f in candidates[:limit]]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def merge_food(
    source_id: int = Field(..., description="The duplicate; it is deleted."),
    target_id: int = Field(..., description="The food that stays."),
) -> dict:
    """Merge a duplicate food into another: every recipe ingredient, shopping list
    entry and cook reference moves to the target, then the duplicate is deleted.
    The duplicate's own pack size and nutrition values are dropped. Cannot be undone."""
    source, target = await asyncio.gather(_get(f"/food/{source_id}/"), _get(f"/food/{target_id}/"))
    r = await _send("PUT", f"/food/{source_id}/merge/{target_id}/", {})
    return {"merged": source.get("name"), "into": target.get("name"), "target_id": target_id, "message": r.get("msg")}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def set_food_stock(
    foods: list[str] = Field(..., min_length=1, description="Food names as Tandoor has them (see search_food)."),
    on_hand: bool | None = Field(None, description="True: in stock now. False: used up."),
    never_on_shopping_list: bool | None = Field(None, description="True for staples like salt and oil that a recipe should never put on the list."),
) -> dict:
    """Mark foods as on hand (in stock) or as never going on the shopping list. On
    hand is what Tandoor shows in the shopping list and can leave out when a recipe
    goes on it; never_on_shopping_list leaves the food out always."""
    if on_hand is None and never_on_shopping_list is None:
        raise RuntimeError("give on_hand, never_on_shopping_list or both")
    ids, names, missing = [], [], {}
    for name in foods:
        match, similar = fm.match_food(name, await _food_candidates(name))
        if match is None:
            missing[name] = [f["name"] for f in similar]
        else:
            ids.append(match["id"])
            names.append(match["name"])
    if missing:
        raise RuntimeError(f"no food with these names, nothing changed: {missing} (similar names listed)")
    body: dict[str, Any] = {"foods": ids}
    if on_hand is not None:
        body["on_hand"] = on_hand
    if never_on_shopping_list is not None:
        body["ignore_shopping"] = never_on_shopping_list
    async with _client() as c:
        r = await c.put("/food/batch_update/", json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Tandoor answered {r.status_code}: {r.text[:500]}")
    prefs = await _get("/user-preference/")
    prefs = prefs[0] if isinstance(prefs, list) and prefs else prefs
    return {
        "foods": names,
        "on_hand": on_hand,
        "never_on_shopping_list": never_on_shopping_list,
        "recipes_skip_on_hand_foods": bool((prefs or {}).get("mealplan_autoexclude_onhand")),
    }


# --- keywords and meal types -------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def create_keyword(name: str = Field(..., min_length=1), description: str = "") -> dict:
    """Create a keyword (tag). Returns the existing one if the name is taken."""
    r = await _send("POST", "/keyword/", {"name": name.strip(), "description": description})
    return {"id": r.get("id"), "name": r.get("name")}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def merge_keyword(
    source_id: int = Field(..., description="The keyword that goes away (see list_keywords)."),
    target_id: int = Field(..., description="The keyword that stays."),
) -> dict:
    """Merge one keyword into another: every recipe tagged with the source gets
    the target, then the source is deleted. Cannot be undone."""
    source, target = await asyncio.gather(_get(f"/keyword/{source_id}/"), _get(f"/keyword/{target_id}/"))
    r = await _send("PUT", f"/keyword/{source_id}/merge/{target_id}/", {})
    return {"merged": source.get("name"), "into": target.get("name"), "message": r.get("msg")}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def create_meal_type(
    name: str = Field(..., min_length=1),
    default_time: str | None = Field(None, description="HH:MM, the time a plan entry of this type gets."),
) -> dict:
    """Create a meal type (e.g. 'Meal Prep'). Returns the existing one if the name is
    taken. Tandoor has no merge for meal types; move entries with move_meal_plan."""
    body: dict[str, Any] = {"name": name.strip()}
    if default_time:
        body["time"] = default_time
    r = await _send("POST", "/meal-type/", body)
    return {"id": r.get("id"), "name": r.get("name"), "default_time": r.get("time")}


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
