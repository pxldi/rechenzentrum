"""Calendar and task tools over CalDAV, aimed at Nextcloud's Calendar and Tasks apps.

Every datetime the tools take or give is ISO 8601. Input without an offset
is read as Europe/Berlin; output always carries the offset. All-day events
are dates (YYYY-MM-DD) with no time, in and out. Tasks (VTODO) live in the
same collections as events; a list is a calendar that accepts tasks.

With OAUTH_ISSUER set the server asks for an Authentik-issued bearer token on
every /mcp request; that is how the copy claude.ai reaches runs. See oauth.py.
"""

import os
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import caldav
import recurring_ical_events
from caldav.lib.error import DAVError
from caldav.lib.vcal import create_ical
from icalendar import Calendar, Todo, vRecur
from mcp.server import MCPServer
from pydantic import Field

from oauth import server_kwargs
from serve import guarded

mcp = MCPServer("calendar", **server_kwargs())

URL = os.environ.get("CALDAV_URL", "http://nextcloud.nextcloud.svc.cluster.local:8080/remote.php/dav/").rstrip("/") + "/"
USER = os.environ.get("CALDAV_USER", "")
PASSWORD = os.environ.get("CALDAV_PASSWORD", "")
# Nextcloud only answers to its trusted_domains, and the in-cluster Service
# name is not one of them; the public name is sent as Host instead.
HOST = os.environ.get("CALDAV_HOST", "")
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Berlin"))
# Nextcloud's own bookkeeping collections; nothing a person plans lives there.
HIDDEN = {"inbox", "outbox", "trashbin"}
# Collections Nextcloud fills itself and refuses writes to: the birthdays
# calendar is generated from the address book.
READ_ONLY = {"contact_birthdays"}

ERRORS = (DAVError, RuntimeError, ValueError, OSError)


def _client() -> caldav.DAVClient:
    if not USER or not PASSWORD:
        raise RuntimeError("CALDAV_USER / CALDAV_PASSWORD are not set")
    headers = {"Host": HOST} if HOST else {}
    return caldav.DAVClient(url=URL, username=USER, password=PASSWORD, headers=headers, timeout=30)


def _slug(cal: caldav.Calendar) -> str:
    return str(cal.url).rstrip("/").rsplit("/", 1)[-1]


def _calendars(client: caldav.DAVClient) -> list[caldav.Calendar]:
    return [c for c in client.principal().calendars() if _slug(c) not in HIDDEN]


def _writable(cal: caldav.Calendar) -> caldav.Calendar:
    if _slug(cal) in READ_ONLY:
        raise RuntimeError(f"{cal.name or _slug(cal)!r} is read-only (Nextcloud fills it from the contacts)")
    return cal


def _calendar(client: caldav.DAVClient, name: str) -> caldav.Calendar:
    wanted = name.strip().lower()
    for c in _calendars(client):
        if wanted in {_slug(c).lower(), (c.name or "").lower()}:
            return c
    raise RuntimeError(f"no calendar named {name!r}; known: {[c.name or _slug(c) for c in _calendars(client)]}")


def _components(cal: caldav.Calendar) -> list[str]:
    if _slug(cal) in READ_ONLY:
        return ["VEVENT"]
    try:
        return [str(c).upper() for c in cal.get_supported_components()]
    except ERRORS:
        return ["VEVENT", "VTODO"]


def _task_list(client: caldav.DAVClient, name: str) -> caldav.Calendar:
    """The named list, or with no name the first one that holds only tasks
    (a list made in the Tasks app), else Personal."""
    if name.strip():
        return _writable(_calendar(client, name))
    cals = _calendars(client)
    for c in cals:
        if _components(c) == ["VTODO"]:
            return c
    return _calendar(client, "Personal")


def _parse_when(value: str, all_day: bool = False) -> date | datetime:
    value = value.strip()
    if all_day or (len(value) == 10 and value[4] == "-"):
        return date.fromisoformat(value[:10])
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def _fmt(value: Any) -> str | None:
    if value is None:
        return None
    v = getattr(value, "dt", value)
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=TZ)
        return v.astimezone(TZ).isoformat(timespec="minutes")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _event_dict(ev: caldav.Event, calendar: caldav.Calendar) -> dict:
    return _component_dict(ev.icalendar_component, calendar)


def _component_dict(c: Any, calendar: caldav.Calendar) -> dict:
    start = c.get("dtstart")
    end = c.get("dtend")
    is_all_day = start is not None and not isinstance(start.dt, datetime)
    return {
        "uid": str(c.get("uid") or ""),
        "calendar": calendar.name or _slug(calendar),
        "summary": str(c.get("summary") or ""),
        "start": _fmt(start),
        "end": _fmt(end),
        "all_day": is_all_day,
        "location": str(c.get("location") or "") or None,
        "description": (str(c.get("description") or "")[:300]) or None,
        "recurring": bool(c.get("rrule")) or bool(c.get("recurrence-id")),
        # One occurrence of a series: pass it as occurrence to move_event,
        # update_event or delete_event to change only this one.
        "occurrence": _fmt(c.get("recurrence-id")),
    }


def _task_dict(t: caldav.Todo, calendar: caldav.Calendar) -> dict:
    c = t.icalendar_component
    status = str(c.get("status") or "NEEDS-ACTION")
    return {
        "uid": str(c.get("uid") or ""),
        "list": calendar.name or _slug(calendar),
        "summary": str(c.get("summary") or ""),
        "due": _fmt(c.get("due")),
        "start": _fmt(c.get("dtstart")),
        "priority": int(c.get("priority") or 0) or None,
        "status": status,
        "done": status == "COMPLETED",
        "completed": _fmt(c.get("completed")),
        "percent": int(c.get("percent-complete") or 0) or None,
        "description": (str(c.get("description") or "")[:300]) or None,
        "categories": [str(x) for x in _categories(c)] or None,
        "parent": _parent(c),
    }


def _parent(c: Any) -> str | None:
    # The caldav library also writes RELTYPE=CHILD links onto a parent when a
    # subtask is saved; only a PARENT link (the default reltype) names one.
    rel = c.get("related-to")
    for r in rel if isinstance(rel, list) else [rel] if rel is not None else []:
        if str(r.params.get("RELTYPE", "PARENT")).upper() == "PARENT":
            return str(r)
    return None


def _categories(c: Any) -> list:
    cats = c.get("categories")
    if cats is None:
        return []
    items = cats if isinstance(cats, list) else [cats]
    return [cat for item in items for cat in getattr(item, "cats", [item])]


def _find_task(client: caldav.DAVClient, uid: str) -> tuple[caldav.Todo, caldav.Calendar]:
    for cal in _calendars(client):
        if "VTODO" not in _components(cal):
            continue
        try:
            return cal.todo_by_uid(uid), cal
        except Exception:  # noqa: BLE001 - not in this list, try the next
            continue
    raise RuntimeError(f"no task with uid {uid!r} in any list")


def _set(c: Any, key: str, value: Any) -> None:
    if c.get(key) is not None:
        c.pop(key)
    if value is not None:
        c.add(key, value)


def _find(client: caldav.DAVClient, uid: str) -> tuple[caldav.Event, caldav.Calendar]:
    for cal in _calendars(client):
        try:
            return cal.event_by_uid(uid), cal
        except Exception:  # noqa: BLE001 - not in this calendar, try the next
            continue
    raise RuntimeError(f"no event with uid {uid!r} in any calendar")


OCCURRENCE = Field(
    "",
    description=(
        "For a recurring event: the occurrence field from list_events or agenda, to change "
        "only that one. Empty changes the whole series."
    ),
)


def _master(ev: caldav.Event) -> Any:
    for comp in ev.icalendar_instance.walk("VEVENT"):
        if comp.get("recurrence-id") is None:
            return comp
    raise RuntimeError("the event has no master component")


def _occurrence_key(master: Any, occurrence: str) -> date | datetime:
    """The RECURRENCE-ID for an occurrence, in the master's own form: a date
    for an all-day series, else a time in the series' zone."""
    first = master.get("dtstart").dt
    if not isinstance(first, datetime):
        return _parse_when(occurrence, all_day=True)
    when = _parse_when(occurrence)
    if not isinstance(when, datetime):
        raise ValueError("occurrence needs the time of the occurrence, as list_events gives it")
    return when.astimezone(first.tzinfo) if first.tzinfo else when.astimezone(TZ).replace(tzinfo=None)


def _same(a: Any, b: Any) -> bool:
    a, b = getattr(a, "dt", a), getattr(b, "dt", b)
    if isinstance(a, datetime) != isinstance(b, datetime):
        return False
    if isinstance(a, datetime):
        a = a if a.tzinfo else a.replace(tzinfo=TZ)
        b = b if b.tzinfo else b.replace(tzinfo=TZ)
    return a == b


def _in_series(ev: caldav.Event, key: date | datetime) -> bool:
    day = key.date() if isinstance(key, datetime) else key
    for inst in recurring_ical_events.of(ev.icalendar_instance).at(day):
        rid = inst.get("recurrence-id") or inst.get("dtstart")
        if _same(rid, key):
            return True
    return False


def _override(ev: caldav.Event, occurrence: str) -> Any:
    """The component for one occurrence, made from the master if the series
    has none for it yet. Raises if the series has no such occurrence."""
    master = _master(ev)
    if master.get("rrule") is None:
        raise ValueError("this event is not recurring; leave occurrence empty")
    key = _occurrence_key(master, occurrence)
    for comp in ev.icalendar_instance.walk("VEVENT"):
        rid = comp.get("recurrence-id")
        if rid is not None and _same(rid, key):
            return comp
    if not _in_series(ev, key):
        raise ValueError(f"the series has no occurrence at {occurrence}")
    first = master.get("dtstart").dt
    end = master.get("dtend")
    length = (end.dt - first) if end is not None else (timedelta(hours=1) if isinstance(first, datetime) else timedelta(days=1))
    comp = master.copy()
    for k in ("rrule", "rdate", "exdate", "dtstart", "dtend", "duration", "recurrence-id"):
        while comp.get(k) is not None:
            comp.pop(k)
    comp.add("recurrence-id", key)
    comp.add("dtstart", key)
    comp.add("dtend", key + length)
    ev.icalendar_instance.add_component(comp)
    return comp


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(*ERRORS)
def list_calendars() -> list[dict]:
    """The calendars and task lists this account can see, with the name to use in
    other tools. holds says whether one takes events, tasks or both."""
    client = _client()
    out = []
    for c in _calendars(client):
        comps = _components(c)
        holds = [k for k, v in (("events", "VEVENT"), ("tasks", "VTODO")) if v in comps]
        out.append({"name": c.name or _slug(c), "id": _slug(c), "holds": holds, "read_only": _slug(c) in READ_ONLY})
    return out


def _list_events(from_date: str, to_date: str, calendar: str = "") -> list[dict]:
    client = _client()
    start = datetime.combine(date.fromisoformat(from_date), datetime.min.time(), TZ)
    end = datetime.combine(date.fromisoformat(to_date) + timedelta(days=1), datetime.min.time(), TZ)
    cals = [_calendar(client, calendar)] if calendar else _calendars(client)
    out = []
    for cal in cals:
        for ev in cal.search(start=start, end=end, event=True, expand=True):
            out.append(_event_dict(ev, cal))
    return sorted(out, key=lambda e: (e["start"] or "", e["summary"]))


@mcp.tool()
@guarded(*ERRORS)
def list_events(
    from_date: str = Field(..., description="YYYY-MM-DD, inclusive"),
    to_date: str = Field(..., description="YYYY-MM-DD, inclusive"),
    calendar: str = Field("", description="Calendar name or id; empty means all calendars."),
) -> list[dict]:
    """Events between two days, recurring ones expanded, sorted by start. Times carry
    the Europe/Berlin offset; all-day events show the date only."""
    return _list_events(from_date, to_date, calendar)


@mcp.tool()
@guarded(*ERRORS)
def search_events(
    query: str = Field(..., description="Text matched against summary, location and description, case-insensitive."),
    days_back: int = Field(30, ge=0, le=730),
    days_ahead: int = Field(180, ge=0, le=730),
) -> list[dict]:
    """Find events by text in a window around today."""
    today = date.today()
    q = query.strip().lower()
    hits = [
        e
        for e in _list_events((today - timedelta(days=days_back)).isoformat(), (today + timedelta(days=days_ahead)).isoformat())
        if q in " ".join(filter(None, [e["summary"], e["location"], e["description"]])).lower()
    ]
    return hits[:50]


@mcp.tool()
@guarded(*ERRORS)
def agenda(
    from_date: str = Field(..., description="YYYY-MM-DD, inclusive"),
    to_date: str = Field("", description="YYYY-MM-DD, inclusive. Empty: the same day."),
) -> dict:
    """A day or a range at a glance: events from every calendar (series expanded)
    and the open tasks due by the end of it, overdue ones included."""
    to_date = to_date or from_date
    tasks = [t for t in list_tasks(list_name="", include_done=False) if t["due"] and t["due"][:10] <= to_date]
    return {"events": _list_events(from_date, to_date), "tasks_due": tasks}


# --- write tools -----------------------------------------------------------


@mcp.tool()
@guarded(*ERRORS)
def create_event(
    summary: str,
    start: str = Field(..., description="ISO datetime (2026-09-20T14:00) or a date for an all-day event."),
    end: str = Field("", description="ISO datetime or date. Empty: one hour after start, or the same day for all-day."),
    calendar: str = Field("Personal", description="Calendar name or id (see list_calendars)."),
    location: str = "",
    description: str = "",
    repeat: str = Field(
        "",
        description=(
            "RFC 5545 RRULE for a series; start and end are the first occurrence. "
            "FREQ=WEEKLY repeats on start's weekday with no end; add COUNT=10 or "
            "UNTIL=20261231 to stop it, BYDAY=MO,WE for several weekdays, INTERVAL=2 "
            "for every other week. Empty: a single event."
        ),
    ),
) -> dict:
    """Create an event or, with repeat, a recurring series. Returns its uid, which
    move_event, update_event and delete_event take."""
    client = _client()
    cal = _writable(_calendar(client, calendar))
    dtstart = _parse_when(start)
    if isinstance(dtstart, datetime):
        dtend = _parse_when(end) if end else dtstart + timedelta(hours=1)
    else:
        dtend = (_parse_when(end, all_day=True) if end else dtstart) + timedelta(days=1)
    if dtend <= dtstart:
        raise ValueError("end must be after start")
    rrule = vRecur.from_ical(repeat.strip().removeprefix("RRULE:")) if repeat.strip() else None
    if rrule is not None and "FREQ" not in rrule:
        raise ValueError("repeat needs FREQ, e.g. FREQ=WEEKLY")
    ical = Calendar.from_ical(
        create_ical(dtstart=dtstart, dtend=dtend, summary=summary, location=location or None, description=description or None, rrule=rrule)
    )
    # Without a VTIMEZONE a client may read TZID=Europe/Berlin as UTC or as
    # floating time, and a weekly series would drift by an hour at the DST
    # change.
    ical.add_missing_timezones()
    ev = cal.add_event(ical.to_ical().decode())
    return _event_dict(ev, cal)


@mcp.tool()
@guarded(*ERRORS)
def move_event(
    uid: str,
    start: str = Field(..., description="New start, ISO datetime or date."),
    end: str = Field("", description="New end. Empty keeps the event's duration."),
    occurrence: str = OCCURRENCE,
) -> dict:
    """Move an event (by uid) to a new start, keeping its duration unless end is given.
    For a recurring event this moves the whole series, or with occurrence just that one."""
    client = _client()
    ev, cal = _find(client, uid)
    _writable(cal)
    c = _override(ev, occurrence) if occurrence.strip() else _master(ev)
    old_start, old_end = c.get("dtstart").dt, (c.get("dtend").dt if c.get("dtend") else None)
    new_start = _parse_when(start, all_day=not isinstance(old_start, datetime))
    if end:
        new_end = _parse_when(end, all_day=not isinstance(old_start, datetime))
    elif old_end is not None:
        new_end = new_start + (old_end - old_start)
    else:
        new_end = new_start + (timedelta(hours=1) if isinstance(new_start, datetime) else timedelta(days=1))
    c.pop("dtstart")
    c.add("dtstart", new_start)
    if c.get("dtend") is not None:
        c.pop("dtend")
    c.add("dtend", new_end)
    ev.save()
    return _component_dict(c, cal)


@mcp.tool()
@guarded(*ERRORS)
def update_event(
    uid: str,
    summary: str = Field("", description="New title. Empty keeps it."),
    location: str | None = Field(None, description="New location; an empty string clears it, null keeps it."),
    description: str | None = Field(None, description="New description; an empty string clears it, null keeps it."),
    occurrence: str = OCCURRENCE,
) -> dict:
    """Change an event's title, location or description. Use move_event for its time.
    For a recurring event this changes the whole series, or with occurrence just that one."""
    client = _client()
    ev, cal = _find(client, uid)
    _writable(cal)
    c = _override(ev, occurrence) if occurrence.strip() else _master(ev)
    if summary.strip():
        _set(c, "summary", summary.strip())
    if location is not None:
        _set(c, "location", location or None)
    if description is not None:
        _set(c, "description", description or None)
    ev.save()
    return _component_dict(c, cal)


@mcp.tool()
@guarded(*ERRORS)
def delete_event(uid: str, occurrence: str = OCCURRENCE) -> dict:
    """Delete an event by uid; for a recurring event the whole series, or with
    occurrence only that one. Nextcloud keeps a deleted series in the calendar trash
    bin for a while; a single occurrence is an exception on the series instead."""
    client = _client()
    ev, cal = _find(client, uid)
    _writable(cal)
    master = _master(ev)
    summary = str(master.get("summary") or "")
    if occurrence.strip():
        comp = _override(ev, occurrence)
        key = comp.get("recurrence-id").dt
        ev.icalendar_instance.subcomponents.remove(comp)
        master.add("exdate", key)
        ev.save()
        return {"deleted": uid, "occurrence": _fmt(key), "summary": summary, "calendar": cal.name or _slug(cal)}
    ev.delete()
    return {"deleted": uid, "summary": summary, "calendar": cal.name or _slug(cal)}


# --- tasks -----------------------------------------------------------------


@mcp.tool()
@guarded(*ERRORS)
def list_tasks(
    list_name: str = Field("", description="List name or id (see list_calendars); empty means every list."),
    include_done: bool = Field(False, description="Also return completed tasks."),
) -> list[dict]:
    """Open tasks, sorted by due date and then priority (1 is highest, 9 lowest).
    Subtasks carry their parent's uid in parent."""
    client = _client()
    cals = [_calendar(client, list_name)] if list_name.strip() else [c for c in _calendars(client) if "VTODO" in _components(c)]
    out = []
    for cal in cals:
        for t in cal.get_todos(include_completed=include_done):
            out.append(_task_dict(t, cal))
    out.sort(key=lambda t: (t["done"], t["due"] or "9999", t["priority"] or 10, t["summary"]))
    return out[:200]


@mcp.tool()
@guarded(*ERRORS)
def create_task(
    summary: str,
    list_name: str = Field("", description="List name or id. Empty: the first tasks-only list, else Personal."),
    due: str = Field("", description="ISO datetime (2026-09-20T14:00) or a date. Empty: no due date."),
    priority: int = Field(0, ge=0, le=9, description="1 high, 5 medium, 9 low; 0 none."),
    description: str = "",
    parent_uid: str = Field("", description="Make this a subtask of the task with that uid."),
) -> dict:
    """Create a task. Returns its uid, which update_task, complete_task and delete_task take."""
    client = _client()
    cal = _task_list(client, list_name)
    todo = Todo()
    todo.add("uid", f"{uuid4()}")
    todo.add("dtstamp", datetime.now(TZ))
    todo.add("summary", summary.strip())
    todo.add("status", "NEEDS-ACTION")
    if due.strip():
        todo.add("due", _parse_when(due))
    if priority:
        todo.add("priority", priority)
    if description:
        todo.add("description", description)
    if parent_uid.strip():
        todo.add("related-to", parent_uid.strip())
    ical = Calendar()
    ical.add("prodid", "-//rechenzentrum//calendar-mcp//EN")
    ical.add("version", "2.0")
    ical.add_component(todo)
    ical.add_missing_timezones()
    t = cal.add_todo(ical.to_ical().decode())
    return _task_dict(t, cal)


@mcp.tool()
@guarded(*ERRORS)
def update_task(
    uid: str,
    summary: str = Field("", description="New title. Empty keeps it."),
    due: str | None = Field(None, description="New due, ISO datetime or date; an empty string clears it, null keeps it."),
    priority: int | None = Field(None, ge=0, le=9, description="1 high, 5 medium, 9 low, 0 clears; null keeps it."),
    description: str | None = Field(None, description="New description; an empty string clears it, null keeps it."),
    percent: int | None = Field(None, ge=0, le=100, description="Progress in percent; null keeps it."),
) -> dict:
    """Change a task's title, due date, priority, description or progress. Use
    complete_task to tick it off."""
    client = _client()
    t, cal = _find_task(client, uid)
    _writable(cal)
    c = t.icalendar_component
    if summary.strip():
        _set(c, "summary", summary.strip())
    if due is not None:
        _set(c, "due", _parse_when(due) if due.strip() else None)
    if priority is not None:
        _set(c, "priority", priority or None)
    if description is not None:
        _set(c, "description", description or None)
    if percent is not None:
        _set(c, "percent-complete", percent or None)
        if percent and c.get("status") in (None, "NEEDS-ACTION"):
            _set(c, "status", "IN-PROCESS")
    t.save()
    return _task_dict(t, cal)


@mcp.tool()
@guarded(*ERRORS)
def complete_task(
    uid: str,
    done: bool = Field(True, description="False reopens a completed task."),
) -> dict:
    """Tick a task off, or reopen it. A recurring task moves on to its next occurrence."""
    client = _client()
    t, cal = _find_task(client, uid)
    if done:
        t.complete(handle_rrule=True)
    else:
        t.uncomplete()
    return _task_dict(t, cal)


@mcp.tool()
@guarded(*ERRORS)
def delete_task(uid: str) -> dict:
    """Delete a task by uid. Nextcloud keeps it in the trash bin for a while."""
    client = _client()
    t, cal = _find_task(client, uid)
    summary = str(t.icalendar_component.get("summary") or "")
    t.delete()
    return {"deleted": uid, "summary": summary, "list": cal.name or _slug(cal)}
