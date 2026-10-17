"""openGym's state document, read and changed without the network.

openGym (gitlab.com/DuarteSantos8/opengym) keeps a profile as one JSON
document. Everything here works on that document, so the tests need neither
the SDK nor a server. Field names and rules follow openGym 1.3.9:

- workouts[]  {id, d, start, end, name, routineIds, routineId, bw, entries,
               prs, vol, _ts}; an entry is {id, sets, topW, target, rid?,
               planned?, noProg?}; a set is {w, r, done} with `phase:
               "warmup"` (or the older `warmup: true`) on warm-ups, `sec` on
               timed rows (frontend/src/lib/finish-workout.js, workout-model.js)
- routines[]  {id, name, ex: [{id, sets, reps, repsMin, weight, mode, prog,
               inc, side, bodyweight, ...}], prog}; `week` maps "0" (Sunday)
               to "6" to routine ids
- bodyweight[] {d, w, t}, all weights in `unit` ("kg" or "lb")
- customEx[]  {id, n, bp, eq, ...}

The progression rules are a port of frontend/src/lib/progression.js
(nextPrescription) for the linear, Greyskull, double and time policies. Two
things are simpler than the app: a deload backs off by the factor
(deloadTo) instead of the app's Epley search for a load and rep pair, and
the "start planned sessions from the last session" profile option is not
read. The app computes its own numbers when a session starts; these are for
talking about the plan.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Exercise names and attributes from openGym's frontend/src/lib/exercises-data.js
# (1.3.9), which takes them from github.com/hasaneyldrm/exercises-dataset under
# the MIT license (EXERCISES-LICENSE beside this file). id -> [name, body part,
# equipment, target muscle]. Images and animations are not included.
_CATALOGUE: dict[str, list[str]] = json.loads((Path(__file__).with_name("exercises.json")).read_text(encoding="utf-8"))

# frontend/src/lib/exercises.js
_BODYWEIGHT_EQ = {"body weight", "band", "resistance band"}
_LOADED_EQ = {
    "barbell", "ez barbell", "olympic barbell", "trap bar", "dumbbell", "kettlebell", "cable",
    "leverage machine", "smith machine", "sled machine", "weighted",
}
_HEAVY_BP = {"upper legs", "lower legs", "back", "hips", "glutes"}
_ASSISTED = re.compile(r"\bassist(ed)?\b", re.I)

# frontend/src/lib/progression.js
POLICIES_FOR = {"reps": ["off", "linear", "greyskull", "double"], "time": ["off", "time"], "cardio": ["off"]}
DELOAD_FACTOR = 0.9
DELOAD_AFTER = {"linear": 3, "greyskull": 1, "double": 3, "time": 3}
DEFAULT_SEC_INCREMENT = 5
MAX_BW_SETS = 6

# Workouts this server logs carry this prefix, so delete_workout can be held
# to them. openGym's own ids are base-36 time plus random characters and never
# contain a dash.
MCP_ID_PREFIX = "mcp-"


class StateError(Exception):
    """A request that does not fit the document. The message is for the model."""


# --- small helpers ---------------------------------------------------------


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) else None


def _records(v: object) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _round1(v: float) -> float:
    return math.floor(v * 10 + 0.5) / 10


def _tidy(v: float | None) -> float | int | None:
    """8.0 -> 8, so numbers read the way the app shows them."""
    if v is None:
        return None
    r = round(v, 3)
    return int(r) if r == int(r) else r


def unit_of(state: dict) -> str:
    return "lb" if state.get("unit") == "lb" else "kg"


def local_day(ms: float, tz: ZoneInfo) -> date | None:
    try:
        return datetime.fromtimestamp(ms / 1000, tz).date()
    except (OverflowError, OSError, ValueError):
        return None


def workout_day(w: dict, tz: ZoneInfo) -> date | None:
    """The day openGym files the workout under: its own `d`, else the start."""
    d = w.get("d")
    if isinstance(d, str):
        try:
            return date.fromisoformat(d[:10])
        except ValueError:
            pass
    start = _num(w.get("start"))
    return local_day(start, tz) if start is not None else None


def make_id() -> str:
    return f"{MCP_ID_PREFIX}{int(time.time() * 1000):x}{secrets.token_hex(3)}"


# --- exercises -------------------------------------------------------------


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    bodypart: str = ""
    equipment: str = ""
    target: str = ""
    custom: bool = False
    assisted_flag: bool | None = None

    @property
    def assisted(self) -> bool:
        if self.assisted_flag is not None:
            return self.assisted_flag
        return self.equipment == "leverage machine" and bool(_ASSISTED.search(self.name))

    @property
    def bodyweight_eq(self) -> bool:
        return self.equipment in _BODYWEIGHT_EQ

    @property
    def loaded_eq(self) -> bool:
        return self.equipment in _LOADED_EQ

    @property
    def cardio(self) -> bool:
        return self.bodypart == "cardio"


class Catalogue:
    """The built-in exercises plus the profile's own (customEx)."""

    def __init__(self, state: dict) -> None:
        self._custom: dict[str, Exercise] = {}
        for c in _records(state.get("customEx")):
            cid = c.get("id")
            if isinstance(cid, str) and cid:
                self._custom[cid] = Exercise(
                    id=cid,
                    name=str(c.get("n") or c.get("name") or cid),
                    bodypart=str(c.get("bp") or ""),
                    equipment=str(c.get("eq") or ""),
                    target=str(c.get("tg") or ""),
                    custom=True,
                    assisted_flag=c.get("assisted") if isinstance(c.get("assisted"), bool) else None,
                )

    def get(self, ex_id: object) -> Exercise:
        key = str(ex_id)
        if key in self._custom:
            return self._custom[key]
        row = _CATALOGUE.get(key)
        if row:
            return Exercise(key, row[0], row[1], row[2], row[3])
        return Exercise(key, f"unknown exercise {key}")

    def name(self, ex_id: object) -> str:
        return self.get(ex_id).name

    def all(self) -> Iterable[Exercise]:
        yield from self._custom.values()
        for key, row in _CATALOGUE.items():
            yield Exercise(key, row[0], row[1], row[2], row[3])

    def search(self, query: str, limit: int = 10, prefer: Iterable[str] = ()) -> list[Exercise]:
        """Exercises whose name has every word of the query; the profile's own
        and the ones in `prefer` (used in routines or history) first."""
        words = [w for w in re.split(r"\s+", query.lower().strip()) if w]
        if not words:
            return []
        preferred = set(prefer)
        hits = [e for e in self.all() if all(w in e.name.lower() for w in words)]
        hits.sort(key=lambda e: (e.name.lower() != query.lower().strip(), not e.custom, e.id not in preferred, len(e.name)))
        return hits[:limit]

    def resolve(self, ref: str, prefer: Iterable[str] = ()) -> Exercise:
        """An exercise from an id or a name. A name has to be unambiguous among
        the exercises the profile uses, or exact, or the only match."""
        ref = (ref or "").strip()
        if not ref:
            raise StateError("an exercise is required")
        if ref in self._custom or ref in _CATALOGUE:
            return self.get(ref)
        lower = ref.lower()
        exact = [e for e in self.all() if e.name.lower() == lower]
        if len(exact) == 1:
            return exact[0]
        preferred = set(prefer)
        hits = self.search(ref, limit=200, prefer=preferred)
        used = [e for e in hits if e.id in preferred or e.custom]
        if len(used) == 1:
            return used[0]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise StateError(f"no exercise matches {ref!r}; try find_exercise")
        pool = used or hits
        listed = "; ".join(f"{e.id} {e.name}" for e in pool[:8])
        raise StateError(f"{ref!r} matches several exercises, pass an id: {listed}")


def used_exercise_ids(state: dict) -> list[str]:
    seen: dict[str, None] = {}
    for r in _records(state.get("routines")):
        for c in _records(r.get("ex")):
            if c.get("id") is not None:
                seen[str(c["id"])] = None
    for w in reversed(_records(state.get("workouts"))):
        for e in _records(w.get("entries")):
            if e.get("id") is not None:
                seen[str(e["id"])] = None
    return list(seen)


# --- sets and workouts -----------------------------------------------------


def is_warmup(s: dict) -> bool:
    phase = s.get("phase")
    if isinstance(phase, str) and phase.strip():
        return phase.strip().lower() in ("warmup", "warm-up", "warm_up")
    return s.get("warmup") is True


def _side_set(s: dict) -> bool:
    sides = s.get("sides")
    return isinstance(sides, dict) and isinstance(sides.get("L"), dict) and isinstance(sides.get("R"), dict)


def set_done(s: dict) -> bool:
    if _side_set(s):
        return s["sides"]["L"].get("done") is True or s["sides"]["R"].get("done") is True
    return s.get("done") is True


def set_volume(s: dict) -> float:
    if not s.get("done"):
        return 0.0
    v = (_num(s.get("w")) or 0) * (_num(s.get("r")) or 0)
    drops = [s["sides"]["L"], s["sides"]["R"]] if _side_set(s) else [s]
    for part in drops:
        if part.get("type") == "dropset":
            for d in _records(part.get("drops")):
                v += (_num(d.get("w")) or 0) * (_num(d.get("r")) or 0)
    return v


def epley(weight: float, reps: float) -> float | None:
    if weight <= 0 or reps < 1:
        return None
    return _round1(weight * (1 + reps / 30))


def _best_load(ex: Exercise, loads: list[float]) -> float:
    loads = [w for w in loads if w > 0]
    if not loads:
        return 0.0
    return min(loads) if ex.assisted else max(loads)


def beats(ex: Exercise, w: float, prev: float) -> bool:
    return w > 0 and (prev <= 0 or (w < prev if ex.assisted else w > prev))


def entry_best_weight(ex: Exercise, entry: dict) -> float:
    return _best_load(ex, [_num(s.get("w")) or 0 for s in _records(entry.get("sets")) if set_done(s) and not is_warmup(s)])


def _set_view(s: dict) -> dict:
    out: dict = {}
    if is_warmup(s):
        out["warmup"] = True
    for k, name in (("w", "weight"), ("r", "reps"), ("sec", "seconds"), ("rir", "rir"), ("rpe", "rpe")):
        v = _num(s.get(k))
        if v is not None and (k in ("w", "r") or v):
            out[name] = _tidy(v)
    if s.get("type") in ("dropset", "restpause"):
        out["type"] = s["type"]
        if s["type"] == "dropset":
            out["drops"] = [{"weight": _tidy(_num(d.get("w"))), "reps": _tidy(_num(d.get("r")))} for d in _records(s.get("drops"))]
    if _side_set(s):
        out["per_side"] = {k: {"weight": _tidy(_num(v.get("w"))), "reps": _tidy(_num(v.get("r")))} for k, v in s["sides"].items()}
    if not set_done(s):
        out["done"] = False
    return out


def _duration_min(w: dict) -> float | None:
    start, end = _num(w.get("start")), _num(w.get("end"))
    if start is not None and end is not None and end >= start:
        return round((end - start) / 60000, 1)
    return None


def workout_volume(w: dict) -> float:
    return sum(set_volume(s) for e in _records(w.get("entries")) for s in _records(e.get("sets")) if not is_warmup(s))


def workout_summary(w: dict, cat: Catalogue, tz: ZoneInfo) -> dict:
    entries = _records(w.get("entries"))
    work = [s for e in entries for s in _records(e.get("sets")) if not is_warmup(s)]
    day = workout_day(w, tz)
    start = _num(w.get("start"))
    return {
        "id": w.get("id"),
        "date": day.isoformat() if day else None,
        "start": datetime.fromtimestamp(start / 1000, tz).strftime("%H:%M") if start else None,
        "name": w.get("name") or "",
        "duration_min": _duration_min(w),
        "sets_done": sum(1 for s in work if set_done(s)),
        "volume": _tidy(_round1(_num(w.get("vol")) or workout_volume(w))),
        "exercises": [cat.name(e.get("id")) for e in entries],
        "prs": [cat.name(p) for p in w.get("prs") or [] if isinstance(p, str | int)],
        **({"note": w["note"]} if isinstance(w.get("note"), str) and w["note"] else {}),
    }


def workout_detail(w: dict, cat: Catalogue, tz: ZoneInfo) -> dict:
    out = workout_summary(w, cat, tz)
    out["entries"] = []
    for e in _records(w.get("entries")):
        ex = cat.get(e.get("id"))
        item = {
            "exercise_id": ex.id,
            "exercise": ex.name,
            "sets": [_set_view(s) for s in _records(e.get("sets"))],
        }
        best = entry_best_weight(ex, e)
        if best:
            item["top_weight"] = _tidy(best)
        if isinstance(e.get("note"), str) and e["note"]:
            item["note"] = e["note"]
        out["entries"].append(item)
    return out


def sorted_workouts(state: dict) -> list[dict]:
    """Oldest first, by day and start, as openGym keeps them."""
    ws = _records(state.get("workouts"))
    return sorted(ws, key=lambda w: (str(w.get("d") or ""), _num(w.get("start")) or 0))


def exercise_sessions(state: dict, ex: Exercise, tz: ZoneInfo) -> list[dict]:
    """Every workout that has this exercise, oldest first, with its sets."""
    out = []
    for w in sorted_workouts(state):
        for e in _records(w.get("entries")):
            if str(e.get("id")) != ex.id:
                continue
            sets = _records(e.get("sets"))
            if not any(set_done(s) for s in sets):
                continue
            work = [s for s in sets if set_done(s) and not is_warmup(s)]
            best = entry_best_weight(ex, e)
            # Epley reads the reps of one side on unilateral work.
            per_side = 2 if isinstance(e.get("target"), dict) and e["target"].get("side") else 1
            e1rm = max((epley(_num(s.get("w")) or 0, (_num(s.get("r")) or 0) / per_side) or 0 for s in work), default=0)
            day = workout_day(w, tz)
            out.append({
                "date": day.isoformat() if day else None,
                "workout_id": w.get("id"),
                "workout": w.get("name") or "",
                "sets": [_set_view(s) for s in sets],
                "top_weight": _tidy(best) if best else None,
                "volume": _tidy(_round1(sum(set_volume(s) for s in work))),
                "est_1rm": _tidy(e1rm) if e1rm else None,
            })
    return out


# --- routines --------------------------------------------------------------


def routines(state: dict) -> list[dict]:
    return _records(state.get("routines"))


def find_routine(state: dict, ref: str) -> dict:
    ref = (ref or "").strip()
    rs = routines(state)
    for r in rs:
        if str(r.get("id")) == ref:
            return r
    lower = ref.lower()
    exact = [r for r in rs if str(r.get("name") or "").strip().lower() == lower]
    if len(exact) == 1:
        return exact[0]
    hits = [r for r in rs if lower and lower in str(r.get("name") or "").lower()]
    if len(hits) == 1:
        return hits[0]
    names = ", ".join(str(r.get("name")) for r in rs)
    if not hits:
        raise StateError(f"no routine matches {ref!r}; routines: {names}")
    raise StateError(f"{ref!r} matches several routines: {', '.join(str(r.get('name')) for r in hits)}")


_WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def week_plan(state: dict) -> dict[str, list[str]]:
    by_id = {str(r.get("id")): str(r.get("name") or "") for r in routines(state)}
    week = state.get("week") if isinstance(state.get("week"), dict) else {}
    out = {}
    for i in (1, 2, 3, 4, 5, 6, 0):
        ids = week.get(str(i)) or []
        out[_WEEKDAYS[i]] = [by_id.get(str(x), str(x)) for x in ids] if isinstance(ids, list) else []
    return out


def mode_of(cfg: dict, ex: Exercise) -> str:
    m = cfg.get("mode")
    if m in ("reps", "time", "cardio"):
        return m
    return "cardio" if ex.cardio else "reps"


def is_bw(cfg: dict, ex: Exercise) -> bool:
    return bool(cfg["bodyweight"]) if cfg.get("bodyweight") is not None else ex.bodyweight_eq


def rep_step(cfg: dict) -> int:
    return 2 if cfg.get("side") else 1


def routine_view(r: dict, cat: Catalogue) -> dict:
    exs = []
    for c in _records(r.get("ex")):
        ex = cat.get(c.get("id"))
        item = {"exercise_id": ex.id, "exercise": ex.name, "sets": c.get("sets") or 1}
        mode = mode_of(c, ex)
        if mode == "time":
            item["seconds"] = c.get("sec")
        elif c.get("repsMin") and c.get("prog", r.get("prog")) == "double":
            item["reps"] = f"{c.get('repsMin')}-{c.get('reps')}"
        else:
            item["reps"] = c.get("reps")
        if c.get("weight") is not None:
            item["weight"] = c.get("weight")
        item["progression"] = policy_for(c, r, mode)
        if c.get("side"):
            item["per_side"] = True
        if c.get("note"):
            item["note"] = c["note"]
        exs.append(item)
    return {"id": r.get("id"), "name": r.get("name") or "", "exercises": exs}


# --- progression (port of progression.js nextPrescription) ----------------


def policy_for(cfg: dict, routine: dict | None, mode: str) -> str:
    allowed = POLICIES_FOR.get(mode, ["off"])
    pick = cfg.get("prog") or (routine or {}).get("prog") or ("linear" if mode == "reps" else "off")
    return pick if pick in allowed else "off"


def default_increment(ex: Exercise, unit: str) -> float:
    heavy = ex.bodypart in _HEAVY_BP
    if unit == "lb":
        return 10 if heavy else 5
    return 5 if heavy else 2.5


def snap(v: float, step: float) -> float:
    if not step > 0:
        return _round1(v)
    return _round1(math.floor(v / step + 0.5) * step)


def add_step(w: float, step: float, inc: float) -> float:
    on_grid = inc > 0 and abs(w - math.floor(w / inc + 0.5) * inc) <= 0.1
    nxt = w + step
    return max(0.0, snap(nxt, inc) if on_grid else _round1(nxt))


def deload_to(cur: float, step: float, factor: float = DELOAD_FACTOR) -> float:
    nxt = snap(cur * factor, step)
    if nxt >= cur:
        nxt = snap(cur - step, step)
    return max(step, nxt)


def normalize_rep_range(reps: object, reps_min: object, stride: int = 1) -> tuple[int, int]:
    def pos(v: object, fallback: int) -> int:
        n = _num(v)
        return max(1, round(n)) if n is not None and n > 0 else fallback

    def align(v: int) -> int:
        return max(stride, math.ceil(v / stride) * stride)

    upper = align(pos(reps, 10))
    lower = align(pos(reps_min, max(1, upper - 2)))
    return (lower + stride, lower) if lower >= upper else (upper, lower)


_PLAN_KEYS = ("sets", "reps", "repsMin", "sec")


def planned_of(cfg: dict, ex: Exercise) -> dict:
    mode = mode_of(cfg, ex)
    out: dict = {"sets": max(1, int(_num(cfg.get("sets")) or 1))}
    if mode == "reps" and (_num(cfg.get("reps")) or 0) > 0:
        out["reps"] = cfg["reps"]
    if mode == "reps" and (_num(cfg.get("repsMin")) or 0) > 0:
        out["repsMin"] = cfg["repsMin"]
    if mode == "time" and (_num(cfg.get("sec")) or 0) > 0:
        out["sec"] = cfg["sec"]
    if cfg.get("weight") is not None:
        out["weight"] = cfg["weight"]
    return out


def _same_plan(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in _PLAN_KEYS)


def _entry_rid(w: dict, e: dict) -> str | None:
    if e.get("rid"):
        return e["rid"]
    if any(x.get("rid") for x in _records(w.get("entries"))):
        return None
    ids = w.get("routineIds")
    if isinstance(ids, list) and ids:
        return ids[0]
    return w.get("routineId")


def _read_session(entry: dict, fallback: dict, ex: Exercise) -> dict:
    target = entry.get("target") if isinstance(entry.get("target"), dict) else fallback
    mode = mode_of({**target, "id": ex.id}, ex)
    logged = [s for s in _records(entry.get("sets")) if not is_warmup(s)]
    planned = int(_num(target.get("sets")) or len(logged))
    enough = len(logged) >= planned
    sets = logged[: max(1, planned)]
    done_loads = [_num(s.get("w")) or 0 for s in sets if s.get("done")]
    if ex.assisted:
        loaded = [w for w in done_loads if w > 0]
        weight = min(loaded) if loaded else 0.0
    else:
        weight = max([0.0, *done_loads])
    if mode == "time":
        goal = _num(target.get("sec")) or 0
        held = [(_num(s.get("sec")) or 0) if s.get("done") else 0 for s in sets]
        return {"mode": mode, "target": target, "goal": goal, "weight": weight,
                "ok": goal > 0 and enough and bool(held) and all(h >= goal for h in held)}
    goal = _num(target.get("reps")) or 0
    reps = [(_num(s.get("r")) or 0) if s.get("done") else 0 for s in sets]
    return {
        "mode": mode, "target": target, "goal": goal, "reps": reps, "weight": weight,
        "low": min(reps) if reps else 0, "amrap": reps[-1] if reps else 0,
        "ok": goal > 0 and enough and bool(reps) and all(r >= goal for r in reps),
    }


def _sessions_in(state: dict, ex: Exercise, fallback: dict, rid: str | None) -> list[dict]:
    out = []
    for w in sorted_workouts(state):
        entry = next((e for e in _records(w.get("entries")) if str(e.get("id")) == ex.id and (not rid or _entry_rid(w, e) == rid)), None)
        if entry is None:
            continue
        if w.get("excludeFromProgression") is True or entry.get("noProg") is True:
            continue
        if not any(s.get("done") and not is_warmup(s) for s in _records(entry.get("sets"))):
            continue
        slot = _entry_rid(w, entry)
        s = {"d": w.get("d"), "rid": slot, **_read_session(entry, fallback, ex)}
        if isinstance(entry.get("planned"), dict):
            s["planned"] = entry["planned"]
        out.append(s)
    return out


def _sessions_for(state: dict, ex: Exercise, fallback: dict, rid: str | None) -> list[dict]:
    if rid:
        own = _sessions_in(state, ex, fallback, rid)
        if own:
            return own
    return _sessions_in(state, ex, fallback, None)


def stall_count(sessions: list[dict], policy: str) -> int:
    n = 0
    for i in range(len(sessions) - 1, -1, -1):
        s = sessions[i]
        if s["ok"]:
            break
        if i < len(sessions) - 1 and s["weight"] != sessions[i + 1]["weight"]:
            break
        if i < len(sessions) - 1 and s.get("planned") and sessions[i + 1].get("planned") and not _same_plan(s["planned"], sessions[i + 1]["planned"]):
            break
        if policy == "double":
            run = []
            j = i - 1
            while j >= 0 and sessions[j]["weight"] == s["weight"]:
                run.append(sessions[j]["low"])
                j -= 1
            if run and s["low"] > max(run):
                break
        n += 1
    return n


def next_prescription(state: dict, cfg: dict, routine: dict | None, cat: Catalogue) -> dict:
    """What the next session of this exercise should ask for, and why."""
    ex = cat.get(cfg.get("id"))
    mode = mode_of(cfg, ex)
    policy = policy_for(cfg, routine, mode)
    unit = unit_of(state)
    cfg_inc = _num(cfg.get("inc")) or 0
    inc = (cfg_inc if cfg_inc > 0 else DEFAULT_SEC_INCREMENT) if mode == "time" else (cfg_inc if cfg_inc > 0 else default_increment(ex, unit))
    if policy == "off":
        return {"policy": policy, "kind": "off", "why": "No automatic progression for this exercise."}

    def harder(w: float, step: float) -> float:
        return max(0.0, add_step(w, -step, inc)) if ex.assisted else add_step(w, step, inc)

    def easier(w: float) -> float:
        return add_step(w, inc, inc) if ex.assisted else deload_to(w, inc)

    climbs_reps = is_bw(cfg, ex) or not ex.loaded_eq or ex.assisted
    rid = (routine or {}).get("id")
    sessions = [s for s in _sessions_for(state, ex, cfg, rid) if s["mode"] == mode]
    if not sessions:
        return {"policy": policy, "kind": "first", "why": "Nothing logged yet; this session sets the baseline."}
    last = sessions[-1]
    cfg_weight = _num(cfg.get("weight")) or 0
    cfg_reps = _num(cfg.get("reps")) or 0

    borrowed = bool(rid) and last.get("rid") != rid
    plan_changed = not _same_plan(last["planned"], planned_of(cfg, ex)) if last.get("planned") else borrowed
    if plan_changed:
        why = "First time in this routine; starting from its own target." if borrowed else "Plan changed; starting from the new target."
        set_w = cfg_weight if cfg_weight > 0 and last.get("planned") and last["planned"].get("weight") != cfg.get("weight") else None
        if mode == "time":
            return {"policy": policy, "kind": "hold", "weight": set_w, "seconds": cfg.get("sec") or last["goal"] or None, "why": why}
        if set_w is None and last["weight"] <= 0 and climbs_reps:
            return {"policy": policy, "kind": "hold", "weight": 0, "reps": cfg.get("reps"), "why": why}
        held = set_w if set_w is not None else (last["weight"] if last["weight"] > 0 else (cfg_weight or None))
        if policy == "double":
            top, bottom = normalize_rep_range(cfg.get("reps") or last["goal"] or 10, cfg.get("repsMin"), rep_step(cfg))
            aim = bottom if set_w is not None else min(top, max(bottom, last["low"] + rep_step(cfg)))
            return {"policy": policy, "kind": "hold", "weight": held, "reps": aim, "why": why}
        return {"policy": policy, "kind": "hold", "weight": held, "reps": cfg.get("reps"), "why": why}

    stalls = stall_count(sessions, policy)
    deload_at = DELOAD_AFTER.get(policy, 3)

    if mode == "time":
        if last["ok"]:
            return {"policy": policy, "kind": "up", "seconds": (last["goal"] or _num(cfg.get("sec")) or 0) + inc,
                    "why": f"Held every set for the full time; target up by {_tidy(inc)} s."}
        if stalls >= deload_at:
            sec = deload_to(last["goal"] or _num(cfg.get("sec")) or 0, 5)
            return {"policy": policy, "kind": "deload", "seconds": sec, "why": f"Short {stalls} sessions in a row; back off to {_tidy(sec)} s."}
        return {"policy": policy, "kind": "hold", "seconds": last["goal"] or cfg.get("sec"), "why": "Last time came up short; same target again."}

    w = last["weight"]
    if w <= 0 and climbs_reps:
        goal = last["goal"] or cfg_reps
        plan_sets = max(1, int(_num(cfg.get("sets")) or 1))
        reached = max(plan_sets, int(_num((last.get("target") or {}).get("sets")) or 0)) if last.get("planned") else plan_sets
        keep = {"sets": reached} if reached > plan_sets else {}
        if not last["ok"] or goal <= 0:
            return {"policy": policy, "kind": "hold", "weight": 0, "reps": goal or None, **keep, "why": "Bodyweight; same target again until every set is clean."}
        top = _num(cfg.get("repsMax")) or 0
        if top > 0 and goal >= top:
            sets = reached + 1
            bottom = max(1, min(cfg_reps or top, top))
            if sets <= MAX_BW_SETS:
                return {"policy": policy, "kind": "up", "weight": 0, "reps": bottom, "sets": sets, "why": f"{_tidy(goal)} reps in every set; add a set and go back to {_tidy(bottom)}."}
            return {"policy": policy, "kind": "hold", "weight": 0, "reps": goal, **keep, "why": f"{sets - 1} sets of {_tidy(goal)}; time to add weight or a harder variation."}
        nxt = goal + rep_step(cfg)
        return {"policy": policy, "kind": "up", "weight": 0, "reps": nxt, **keep, "why": f"Bodyweight; every rep last time, so go for {_tidy(nxt)}."}
    if w <= 0:
        return {"policy": policy, "kind": "hold", "weight": cfg_weight or None, "why": "No weight logged last time; enter what you lift."}

    if policy == "double":
        top, bottom = normalize_rep_range(cfg.get("reps") or last["goal"] or 10, cfg.get("repsMin"), rep_step(cfg))
        if last["ok"] and last["low"] >= top:
            return {"policy": policy, "kind": "up", "weight": harder(w, inc), "reps": bottom,
                    "why": f"Top of the rep range in every set; {_tidy(inc)} {unit} {'less help' if ex.assisted else 'more'}, back to {bottom} reps."}
        if stalls >= deload_at:
            dw = easier(w)
            return {"policy": policy, "kind": "deload", "weight": dw, "reps": bottom, "why": f"Stalled {stalls} sessions; deload to {_tidy(dw)} {unit}."}
        aim = min(top, max(bottom, int(last["low"]) + rep_step(cfg)))
        return {"policy": policy, "kind": "hold", "weight": w, "reps": aim, "why": f"Same weight; aim for {aim} reps this time."}

    if last["ok"]:
        dbl = policy == "greyskull" and last["goal"] > 0 and last["amrap"] >= last["goal"] * 2
        step = inc * 2 if dbl else inc
        why = (f"Last set hit {_tidy(last['amrap'])} reps, twice the target; double jump of {_tidy(step)} {unit}." if dbl
               else f"Every rep last time; {_tidy(step)} {unit} {'less help' if ex.assisted else 'more'}.")
        return {"policy": policy, "kind": "up", "weight": harder(w, step), "reps": cfg.get("reps") or (last["goal"] or None), "why": why}
    if stalls >= deload_at:
        dw = easier(w)
        return {"policy": policy, "kind": "deload", "weight": dw, "reps": cfg.get("reps"),
                "why": f"Missed reps {stalls} session{'s' if stalls > 1 else ''} running; reset to {_tidy(dw)} {unit} and work back up."}
    return {"policy": policy, "kind": "hold", "weight": w, "reps": cfg.get("reps"),
            "why": f"Missed reps last time; same weight again ({deload_at - stalls} of {deload_at} to go before a deload)."}


def suggest_routine(state: dict, routine: dict, cat: Catalogue, tz: ZoneInfo) -> dict:
    unit = unit_of(state)
    out = []
    for cfg in _records(routine.get("ex")):
        ex = cat.get(cfg.get("id"))
        p = next_prescription(state, cfg, routine, cat)
        sessions = exercise_sessions(state, ex, tz)
        last = sessions[-1] if sessions else None
        item = {
            "exercise_id": ex.id,
            "exercise": ex.name,
            "policy": p["policy"],
            "kind": p["kind"],
            "next": {k: _tidy(p[k]) if isinstance(p.get(k), int | float) else p.get(k) for k in ("weight", "reps", "sets", "seconds") if p.get(k) is not None},
            "why": p.get("why"),
        }
        if "sets" not in item["next"]:
            item["next"]["sets"] = cfg.get("sets") or 1
        if last:
            item["last"] = {"date": last["date"], "sets": [s for s in last["sets"] if not s.get("warmup")]}
        out.append(item)
    return {"routine": routine.get("name"), "unit": unit, "exercises": out}


# --- changing the document -------------------------------------------------


@dataclass
class SetIn:
    weight: float
    reps: float
    warmup: bool = False


@dataclass
class EntryIn:
    exercise: str
    sets: list[SetIn]
    note: str = ""


def _prior_best(state: dict, ex: Exercise, before: tuple[str, float]) -> float:
    best = 0.0
    for w in _records(state.get("workouts")):
        if (str(w.get("d") or ""), _num(w.get("start")) or 0) >= before:
            continue
        for e in _records(w.get("entries")):
            if str(e.get("id")) == ex.id:
                b = entry_best_weight(ex, e)
                if beats(ex, b, best):
                    best = b
    return best


def add_workout(
    state: dict,
    *,
    day: date,
    entries: list[EntryIn],
    tz: ZoneInfo,
    name: str = "",
    start_hm: str | None = None,
    duration_min: float | None = None,
    routine_ref: str | None = None,
    note: str = "",
    now_ms: int | None = None,
    new_id: str | None = None,
) -> tuple[dict, dict]:
    """A copy of `state` with one finished workout added, and that workout.

    Shaped like a session logged in the app afterwards (doFinishWorkout with
    a backfill): stamped with `_ts`, PR badges against the history before it,
    the per-exercise confirmed weights (exWeights) left alone."""
    if not entries:
        raise StateError("a workout needs at least one exercise")
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    cat = Catalogue(state)
    used = used_exercise_ids(state)
    routine = find_routine(state, routine_ref) if routine_ref else None

    if start_hm:
        try:
            hh, mm = (int(x) for x in start_hm.split(":", 1))
            start_dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
        except ValueError as exc:
            raise StateError(f"start_time must be HH:MM, not {start_hm!r}") from exc
    else:
        start_dt = datetime(day.year, day.month, day.day, 18, 0, tzinfo=tz)
    start_ms = int(start_dt.timestamp() * 1000)
    if start_ms > now_ms:
        raise StateError("the workout would start in the future; give a date and time that has passed")
    dur = duration_min if duration_min and duration_min > 0 else 60
    if dur > 600:
        raise StateError("duration_min is more than ten hours")
    end_ms = min(start_ms + int(dur * 60000), now_ms)

    built = []
    prs = []
    for item in entries:
        ex = cat.resolve(item.exercise, prefer=used)
        if not item.sets:
            raise StateError(f"{ex.name}: no sets given")
        sets = []
        for s in item.sets:
            if s.weight < 0 or s.weight > 1000 or s.reps < 0 or s.reps > 200 or (s.reps == 0 and not s.warmup):
                raise StateError(f"{ex.name}: {s.weight} x {s.reps} is not a set")
            row: dict = {"w": _tidy(s.weight), "r": _tidy(s.reps), "done": True}
            if s.warmup:
                row["phase"] = "warmup"
            sets.append(row)
        cfg = next((c for c in _records((routine or {}).get("ex")) if str(c.get("id")) == ex.id), None)
        entry: dict = {"id": ex.id, "sets": sets, "topW": None, "target": None}
        best = entry_best_weight(ex, entry)
        entry["topW"] = _tidy(best) if best else None
        if cfg is not None:
            entry["target"] = {k: cfg[k] for k in ("sets", "reps", "repsMin", "weight", "mode", "sec", "side", "bodyweight") if k in cfg}
            entry["planned"] = planned_of(cfg, ex)
            entry["rid"] = routine.get("id")
        if item.note.strip():
            entry["note"] = item.note.strip()
        if beats(ex, best, _prior_best(state, ex, (day.isoformat(), start_ms))):
            prs.append(ex.id)
        built.append(entry)

    rid = routine.get("id") if routine else None
    w: dict = {
        "id": new_id or make_id(),
        "d": day.isoformat(),
        "start": start_ms,
        "end": end_ms,
        "routineIds": [rid] if rid else [],
        "routineId": rid,
        "name": name.strip() or (str(routine.get("name")) if routine else "Workout"),
        "entries": built,
        "prs": prs,
        "_ts": now_ms,
    }
    bws = [b for b in _records(state.get("bodyweight")) if isinstance(b.get("d"), str) and b["d"] <= day.isoformat() and _num(b.get("w"))]
    if bws:
        w["bw"] = max(bws, key=lambda b: b["d"])["w"]
    if note.strip():
        w["note"] = note.strip()
    w["vol"] = _tidy(_round1(workout_volume(w)))

    new = json.loads(json.dumps(state))
    new["workouts"] = sorted([*_records(new.get("workouts")), w], key=lambda x: (str(x.get("d") or ""), _num(x.get("start")) or 0))
    new["_ts"] = max(now_ms, int(_num(state.get("_ts")) or 0) + 1)
    return new, w


def remove_workout(state: dict, workout_id: str, now_ms: int | None = None) -> tuple[dict, dict]:
    if not str(workout_id).startswith(MCP_ID_PREFIX):
        raise StateError("only workouts logged through this connector can be deleted here; delete others in the app")
    found = next((w for w in _records(state.get("workouts")) if w.get("id") == workout_id), None)
    if found is None:
        raise StateError(f"no workout with id {workout_id}")
    new = json.loads(json.dumps(state))
    new["workouts"] = [w for w in _records(new.get("workouts")) if w.get("id") != workout_id]
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    new["_ts"] = max(now_ms, int(_num(state.get("_ts")) or 0) + 1)
    return new, found


def set_bodyweight(state: dict, day: date, weight: float, now_ms: int | None = None) -> tuple[dict, dict, dict | None]:
    """A copy with the weigh-in for `day` set (one entry per day, as in the
    app's BwSheet), the new entry and the one it replaced."""
    if not 20 <= weight <= 500:
        raise StateError(f"{weight} is not a body weight")
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    new = json.loads(json.dumps(state))
    log = _records(new.get("bodyweight"))
    iso = day.isoformat()
    old = next((b for b in log if b.get("d") == iso), None)
    entry = {"d": iso, "w": _tidy(weight), "t": now_ms}
    log = [b for b in log if b.get("d") != iso] + [entry]
    log.sort(key=lambda b: str(b.get("d")))
    new["bodyweight"] = log
    new["_ts"] = max(now_ms, int(_num(state.get("_ts")) or 0) + 1)
    return new, entry, old


def check_change(before: dict, after: dict, *, workouts: int = 0, bodyweight: int = 0) -> None:
    """Refuse to send a document that lost anything it should not have."""
    for key in ("routines", "customEx", "week", "dayPlan", "exWeights", "unit"):
        if before.get(key) != after.get(key):
            raise StateError(f"internal check failed: {key} would change")
    if len(_records(after.get("workouts"))) != len(_records(before.get("workouts"))) + workouts:
        raise StateError("internal check failed: workout count")
    if bodyweight >= 0 and len(_records(after.get("bodyweight"))) - len(_records(before.get("bodyweight"))) not in (0, bodyweight):
        raise StateError("internal check failed: weigh-in count")


def parse_day(value: str, tz: ZoneInfo, today: date | None = None) -> date:
    today = today or datetime.now(tz).date()
    v = (value or "").strip().lower()
    if v in ("", "today", "heute"):
        return today
    if v in ("yesterday", "gestern"):
        return today - timedelta(days=1)
    try:
        d = date.fromisoformat(v)
    except ValueError as exc:
        raise StateError(f"date must be YYYY-MM-DD, 'today' or 'yesterday', not {value!r}") from exc
    if d > today:
        raise StateError("that date is in the future")
    return d
