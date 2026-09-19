"""Home Assistant over its REST API: who is home, entity states, and
switching lights and plugs. Needs a long-lived access token."""

import os
from typing import Any

import httpx
from mcp.server import MCPServer
from pydantic import Field

from serve import guarded

mcp = MCPServer("homeassistant")

BASE_URL = os.environ.get("HASS_URL", "http://home-assistant.home-assistant.svc.cluster.local:8123").rstrip("/")
TOKEN = os.environ.get("HASS_TOKEN", "")
# Domains turn_on / turn_off may touch. A switch can be a plug on a heater,
# so the tools stay behind the approval keyboard in the risk profile.
SWITCHABLE = ("light", "switch", "fan", "input_boolean")


def _client() -> httpx.AsyncClient:
    if not TOKEN:
        raise RuntimeError("HASS_TOKEN is not set")
    return httpx.AsyncClient(base_url=f"{BASE_URL}/api", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=20.0)


async def _get(path: str) -> Any:
    async with _client() as c:
        r = await c.get(path)
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> Any:
    async with _client() as c:
        r = await c.post(path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Home Assistant answered {r.status_code}: {r.text[:400]}")
        return r.json()


def _brief(s: dict) -> dict:
    a = s.get("attributes") or {}
    out = {
        "entity_id": s["entity_id"],
        "name": a.get("friendly_name") or s["entity_id"],
        "state": s.get("state"),
        "changed": (s.get("last_changed") or "")[:19],
    }
    for k in ("brightness", "temperature", "current_temperature", "unit_of_measurement", "battery_level", "source_type"):
        if k in a:
            out[k] = a[k]
    return out


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def who_is_home() -> list[dict]:
    """Every person with home/not_home (or a zone name) and when that last changed, plus their trackers."""
    states = await _get("/states")
    people = [_brief(s) for s in states if s["entity_id"].startswith("person.")]
    trackers = [_brief(s) for s in states if s["entity_id"].startswith("device_tracker.")]
    return people + trackers


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_entities(
    domain: str = Field("light", description="Entity domain: light, switch, sensor, binary_sensor, climate, cover, media_player ..."),
) -> list[dict]:
    """Entities of one domain with their current state."""
    states = await _get("/states")
    return [_brief(s) for s in states if s["entity_id"].startswith(domain.strip().lower() + ".")]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def get_state(entity_id: str) -> dict:
    """One entity's state and all its attributes."""
    s = await _get(f"/states/{entity_id.strip()}")
    return {**_brief(s), "attributes": s.get("attributes") or {}}


# --- write tools -----------------------------------------------------------


async def _switch(entity_id: str, service: str, extra: dict | None = None) -> dict:
    entity_id = entity_id.strip()
    domain = entity_id.split(".")[0]
    if domain not in SWITCHABLE:
        raise RuntimeError(f"{entity_id!r} is a {domain}; only {SWITCHABLE} can be switched")
    await _post(f"/services/{domain}/{service}", {"entity_id": entity_id, **(extra or {})})
    return _brief(await _get(f"/states/{entity_id}"))


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def turn_on(
    entity_id: str = Field(..., description="e.g. light.wohnzimmer or switch.eve_energy_20ebo8301"),
    brightness_percent: int | None = Field(None, ge=1, le=100, description="Lights only."),
) -> dict:
    """Switch a light, plug, fan or input boolean on. Returns the new state."""
    extra = {"brightness_pct": brightness_percent} if brightness_percent and entity_id.startswith("light.") else None
    return await _switch(entity_id, "turn_on", extra)


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def turn_off(entity_id: str) -> dict:
    """Switch a light, plug, fan or input boolean off. Returns the new state."""
    return await _switch(entity_id, "turn_off")
