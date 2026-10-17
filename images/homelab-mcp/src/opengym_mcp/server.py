import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from mcp.server import MCPServer
from pydantic import BaseModel, Field

from oauth import server_kwargs
from opengym_mcp import logic as og
from serve import guarded

mcp = MCPServer("opengym", **server_kwargs())

# The Service name: nginx in the web container proxies /api to the API.
BASE_URL = os.environ.get("OPENGYM_URL", "http://opengym.opengym.svc.cluster.local").rstrip("/")
TOKEN = os.environ.get("OPENGYM_TOKEN", "")
TZ = ZoneInfo(os.environ.get("OPENGYM_TZ", "Europe/Berlin"))
# A write that meets a newer document (409) merges onto it and tries again.
_WRITE_ATTEMPTS = 3


class OpenGymError(RuntimeError):
    pass


def _client() -> httpx.AsyncClient:
    if not TOKEN:
        raise OpenGymError("OPENGYM_TOKEN is not set")
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        timeout=20.0,
    )


def _check(r: httpx.Response) -> dict:
    if r.status_code in (401, 403):
        raise OpenGymError("openGym refused the token (expired after 90 days, or signed out everywhere); pair again")
    if r.status_code >= 400 and r.status_code != 409:
        raise OpenGymError(f"openGym answered {r.status_code}: {r.text[:300]}")
    try:
        body = r.json()
    except ValueError as exc:
        raise OpenGymError("openGym returned something that is not JSON") from exc
    if not isinstance(body, dict):
        raise OpenGymError("openGym returned an unexpected answer")
    return body


async def _read() -> tuple[dict, int]:
    async with _client() as c:
        body = _check(await c.get("/api/data"))
    state = body.get("state")
    if not isinstance(state, dict):
        raise OpenGymError("this openGym profile has not synced anything yet")
    return state, int(body.get("rev") or 0)


async def _write(change) -> dict:
    """Apply `change(state) -> (new_state, result)` with openGym's
    compare-and-swap: PUT /api/data with the revision it was read at. A 409
    hands back the current document, and the change is made again on that one,
    so a phone that saved in between loses nothing."""
    state, rev = await _read()
    async with _client() as c:
        for _ in range(_WRITE_ATTEMPTS):
            new, result = change(state)
            new.pop("_rev", None)
            new.pop("active", None)
            body = _check(await c.put("/api/data", json={"state": new, "baseRev": rev}))
            if body.get("ok"):
                return {**result, "rev": body.get("rev")}
            state = body.get("state") if isinstance(body.get("state"), dict) else None
            rev = int(body.get("rev") or 0)
            if state is None:
                raise OpenGymError("openGym reported a conflict without a document")
    raise OpenGymError("openGym kept changing while writing; try again")


def _today():
    return datetime.now(TZ).date()


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def list_workouts(
    days: int = Field(30, ge=1, le=730, description="How far back, in days."),
    limit: int = Field(20, ge=1, le=100),
) -> dict:
    """Finished workouts, newest first: date, name, duration, sets done, volume, exercises and PRs."""
    state, _ = await _read()
    cat = og.Catalogue(state)
    since = _today() - timedelta(days=days)
    ws = [w for w in reversed(og.sorted_workouts(state)) if (og.workout_day(w, TZ) or since) >= since]
    return {"unit": og.unit_of(state), "workouts": [og.workout_summary(w, cat, TZ) for w in ws[:limit]]}


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def get_workout(
    workout_id: str = Field("", description="Id from list_workouts."),
    date: str = Field("", description="Or a day, YYYY-MM-DD; returns every workout of that day."),
) -> dict:
    """One workout set by set: weight, reps and warm-ups for every exercise."""
    state, _ = await _read()
    cat = og.Catalogue(state)
    if workout_id:
        found = [w for w in og.sorted_workouts(state) if w.get("id") == workout_id]
    elif date:
        day = og.parse_day(date, TZ, _today())
        found = [w for w in og.sorted_workouts(state) if og.workout_day(w, TZ) == day]
    else:
        raise og.StateError("give workout_id or date")
    if not found:
        raise og.StateError("no workout found")
    return {"unit": og.unit_of(state), "workouts": [og.workout_detail(w, cat, TZ) for w in found]}


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def exercise_history(
    exercise: str = Field(description="Exercise id or name, e.g. 'barbell bench press'."),
    sessions: int = Field(6, ge=1, le=50, description="How many of the latest sessions to return."),
) -> dict:
    """The latest sessions of one exercise with every set, top weight and estimated 1RM (Epley), plus the all-time best."""
    state, _ = await _read()
    cat = og.Catalogue(state)
    ex = cat.resolve(exercise, prefer=og.used_exercise_ids(state))
    hist = og.exercise_sessions(state, ex, TZ)
    best_w = max((h["top_weight"] or 0 for h in hist), default=0) if not ex.assisted else min((h["top_weight"] for h in hist if h["top_weight"]), default=0)
    best_e = max((h["est_1rm"] or 0 for h in hist), default=0)
    return {
        "exercise_id": ex.id,
        "exercise": ex.name,
        "unit": og.unit_of(state),
        "sessions_total": len(hist),
        "best_weight": best_w or None,
        "best_est_1rm": best_e or None,
        "sessions": list(reversed(hist[-sessions:])),
    }


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def find_exercise(
    query: str = Field(description="Words of the English exercise name, e.g. 'incline dumbbell'."),
    limit: int = Field(10, ge=1, le=30),
) -> list[dict]:
    """Exercise ids by name, from openGym's catalogue and the profile's own exercises. Ones already used come first."""
    state, _ = await _read()
    cat = og.Catalogue(state)
    used = set(og.used_exercise_ids(state))
    return [
        {"id": e.id, "name": e.name, "equipment": e.equipment, "body_part": e.bodypart, "used": e.id in used, **({"custom": True} if e.custom else {})}
        for e in cat.search(query, limit=limit, prefer=used)
    ]


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def list_routines() -> dict:
    """Saved routines with their exercises (sets, reps, weight, progression policy) and the weekday plan."""
    state, _ = await _read()
    cat = og.Catalogue(state)
    return {
        "unit": og.unit_of(state),
        "routines": [og.routine_view(r, cat) for r in og.routines(state)],
        "week": og.week_plan(state),
    }


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def suggest_progression(
    routine: str = Field(description="Routine name or id, e.g. 'Push A'."),
) -> dict:
    """The next session of a routine: per exercise the weight and reps openGym's progression rules call for, why, and what was done last time.

    Follows the routine's policies (linear, double, Greyskull, time). A deload is
    simplified to 90 % of the load; the app's own start screen is authoritative."""
    state, _ = await _read()
    cat = og.Catalogue(state)
    return og.suggest_routine(state, og.find_routine(state, routine), cat, TZ)


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def get_bodyweight(days: int = Field(90, ge=1, le=1460)) -> dict:
    """Weigh-ins of the last `days` days, oldest first, with the latest and the change over the period."""
    state, _ = await _read()
    since = (_today() - timedelta(days=days)).isoformat()
    log = [b for b in og._records(state.get("bodyweight")) if isinstance(b.get("d"), str) and b["d"] >= since and og._num(b.get("w"))]
    log.sort(key=lambda b: b["d"])
    out = [{"date": b["d"], "weight": b["w"]} for b in log]
    return {
        "unit": og.unit_of(state),
        "entries": out,
        "latest": out[-1] if out else None,
        "change": og._tidy(round(log[-1]["w"] - log[0]["w"], 2)) if len(log) > 1 else None,
    }


# --- write tools -----------------------------------------------------------


class SetInput(BaseModel):
    weight: float = Field(description="Load in the profile's unit (see list_workouts' unit). 0 for bodyweight. Assisted machines: the help.")
    reps: float = Field(description="Reps; the total of both sides for per-side exercises.")
    warmup: bool = False


class ExerciseInput(BaseModel):
    exercise: str = Field(description="Exercise id or name; ids from find_exercise or list_routines are safest.")
    sets: list[SetInput] = Field(min_length=1, max_length=20)
    note: str = ""


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def log_workout(
    exercises: list[ExerciseInput] = Field(min_length=1, max_length=20),
    date: str = Field("today", description="YYYY-MM-DD, 'today' or 'yesterday'."),
    start_time: str = Field("", description="HH:MM local time; defaults to 18:00."),
    duration_min: float = Field(60, gt=0, le=600),
    routine: str = Field("", description="Routine name or id this session followed, so progression reads it."),
    name: str = Field("", description="Defaults to the routine's name."),
    note: str = "",
) -> dict:
    """Add a finished workout to openGym, as if logged in the app afterwards. Every set counts as done.

    It syncs to the phone on its next poll. Use it for sessions not tracked live;
    a session running on the phone is saved by the phone."""
    day = og.parse_day(date, TZ, _today())
    entries = [og.EntryIn(e.exercise, [og.SetIn(s.weight, s.reps, s.warmup) for s in e.sets], e.note) for e in exercises]

    def change(state: dict):
        new, w = og.add_workout(
            state, day=day, entries=entries, tz=TZ, name=name, start_hm=start_time or None,
            duration_min=duration_min, routine_ref=routine or None, note=note,
        )
        og.check_change(state, new, workouts=1)
        return new, {"logged": og.workout_detail(w, og.Catalogue(new), TZ)}

    return await _write(change)


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def set_progression_step(
    routine: str = Field(description="Routine name or id."),
    exercise: str = Field(description="Exercise id or name as in list_routines."),
    step: float | None = Field(description="Weight added after a clean session, in the profile's unit, e.g. 2 for dumbbells. null restores the app's default (5 kg legs and back, else 2.5 kg)."),
) -> dict:
    """Set how much weight one exercise of a routine goes up by after a session with every rep, the same per-exercise increment the app's routine editor sets. Syncs to the phone; the app uses it from its next session."""
    def change(state: dict):
        new, result = og.set_step(state, routine, exercise, step, og.Catalogue(state))
        og.check_step_change(state, new, str(og.find_routine(state, routine).get("id")))
        return new, result

    return await _write(change)


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def delete_workout(workout_id: str = Field(description="Id of a workout this connector logged (starts with 'mcp-').")) -> dict:
    """Remove a workout that log_workout added, to correct a mistake. Workouts logged in the app are deleted in the app."""

    def change(state: dict):
        new, w = og.remove_workout(state, workout_id)
        og.check_change(state, new, workouts=-1)
        return new, {"deleted": og.workout_summary(w, og.Catalogue(state), TZ)}

    return await _write(change)


@mcp.tool()
@guarded(httpx.HTTPError, OpenGymError, og.StateError)
async def log_bodyweight(
    weight: float = Field(description="Body weight in the profile's unit."),
    date: str = Field("today", description="YYYY-MM-DD, 'today' or 'yesterday'. One weigh-in per day; a second replaces the first."),
) -> dict:
    """Record a weigh-in in openGym. Snacky's week summary reads it from there."""
    day = og.parse_day(date, TZ, _today())

    def change(state: dict):
        new, entry, old = og.set_bodyweight(state, day, weight)
        og.check_change(state, new, bodyweight=1)
        return new, {"saved": {"date": entry["d"], "weight": entry["w"]}, "replaced": old and old.get("w"), "unit": og.unit_of(state)}

    return await _write(change)
