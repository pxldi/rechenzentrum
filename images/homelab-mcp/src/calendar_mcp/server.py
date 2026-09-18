"""Calendar tools over CalDAV, aimed at Nextcloud's Calendar app.

Every datetime the tools take or give is ISO 8601. Input without an offset
is read as Europe/Berlin; output always carries the offset. All-day events
are dates (YYYY-MM-DD) with no time, in and out.
"""

import os
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import caldav
from caldav.lib.error import DAVError
from mcp.server import MCPServer
from pydantic import Field

from serve import guarded

mcp = MCPServer("calendar")

URL = os.environ.get("CALDAV_URL", "http://nextcloud.nextcloud.svc.cluster.local:8080/remote.php/dav/").rstrip("/") + "/"
USER = os.environ.get("CALDAV_USER", "")
PASSWORD = os.environ.get("CALDAV_PASSWORD", "")
# Nextcloud only answers to its trusted_domains, and the in-cluster Service
# name is not one of them; the public name is sent as Host instead.
HOST = os.environ.get("CALDAV_HOST", "")
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Berlin"))
# Nextcloud's own bookkeeping collections; nothing a person plans lives there.
HIDDEN = {"inbox", "outbox", "trashbin"}

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


def _calendar(client: caldav.DAVClient, name: str) -> caldav.Calendar:
    wanted = name.strip().lower()
    for c in _calendars(client):
        if wanted in {_slug(c).lower(), (c.name or "").lower()}:
            return c
    raise RuntimeError(f"no calendar named {name!r}; known: {[c.name or _slug(c) for c in _calendars(client)]}")


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
    c = ev.icalendar_component
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
    }


def _find(client: caldav.DAVClient, uid: str) -> tuple[caldav.Event, caldav.Calendar]:
    for cal in _calendars(client):
        try:
            return cal.event_by_uid(uid), cal
        except Exception:  # noqa: BLE001 - not in this calendar, try the next
            continue
    raise RuntimeError(f"no event with uid {uid!r} in any calendar")


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(*ERRORS)
def list_calendars() -> list[dict]:
    """The calendars this account can see, with the name to use in other tools."""
    client = _client()
    return [{"name": c.name or _slug(c), "id": _slug(c)} for c in _calendars(client)]


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
) -> dict:
    """Create an event. Returns its uid, which move_event and delete_event take."""
    client = _client()
    cal = _calendar(client, calendar)
    dtstart = _parse_when(start)
    if isinstance(dtstart, datetime):
        dtend = _parse_when(end) if end else dtstart + timedelta(hours=1)
    else:
        dtend = (_parse_when(end, all_day=True) if end else dtstart) + timedelta(days=1)
    if dtend <= dtstart:
        raise ValueError("end must be after start")
    ev = cal.save_event(dtstart=dtstart, dtend=dtend, summary=summary, location=location or None, description=description or None)
    return _event_dict(ev, cal)


@mcp.tool()
@guarded(*ERRORS)
def move_event(
    uid: str,
    start: str = Field(..., description="New start, ISO datetime or date."),
    end: str = Field("", description="New end. Empty keeps the event's duration."),
) -> dict:
    """Move an event (by uid) to a new start, keeping its duration unless end is given."""
    client = _client()
    ev, cal = _find(client, uid)
    c = ev.icalendar_component
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
    return _event_dict(ev, cal)


@mcp.tool()
@guarded(*ERRORS)
def delete_event(uid: str) -> dict:
    """Delete an event by uid. Nextcloud keeps it in the calendar trash bin for a while."""
    client = _client()
    ev, cal = _find(client, uid)
    summary = str(ev.icalendar_component.get("summary") or "")
    ev.delete()
    return {"deleted": uid, "summary": summary, "calendar": cal.name or _slug(cal)}
