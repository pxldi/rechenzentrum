"""Photo tools over the Immich API. Telegram cannot show the pictures
through the bot, so anything worth looking at is handed over as a shared
link that opens in the browser without a login."""

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from mcp.server import MCPServer
from pydantic import Field

from serve import guarded

mcp = MCPServer("immich")

BASE_URL = os.environ.get("IMMICH_URL", "http://immich-server.immich.svc.cluster.local:2283").rstrip("/")
PUBLIC_URL = os.environ.get("IMMICH_PUBLIC_URL", "").rstrip("/")
KEY = os.environ.get("IMMICH_API_KEY", "")


def _client() -> httpx.AsyncClient:
    if not KEY:
        raise RuntimeError("IMMICH_API_KEY is not set")
    return httpx.AsyncClient(base_url=f"{BASE_URL}/api", headers={"x-api-key": KEY, "Accept": "application/json"}, timeout=60.0)


async def _get(path: str, **params: Any) -> Any:
    async with _client() as c:
        r = await c.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> Any:
    async with _client() as c:
        r = await c.post(path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Immich answered {r.status_code}: {r.text[:400]}")
        return r.json()


def _asset(a: dict) -> dict:
    exif = a.get("exifInfo") or {}
    place = ", ".join(p for p in [exif.get("city"), exif.get("country")] if p)
    return {
        "id": a["id"],
        "type": a.get("type"),
        "taken": (a.get("localDateTime") or a.get("fileCreatedAt") or "")[:16],
        "place": place or None,
        "people": [p.get("name") for p in a.get("people") or [] if p.get("name")],
        "favorite": a.get("isFavorite"),
    }


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def search_photos(
    query: str = Field(..., description="Free text, matched by the image model: 'Strand bei Sonnenuntergang', 'Hund im Schnee', 'Kreta'."),
    limit: int = Field(12, ge=1, le=50),
    taken_after: str | None = Field(None, description="YYYY-MM-DD"),
    taken_before: str | None = Field(None, description="YYYY-MM-DD"),
) -> list[dict]:
    """Photos and videos that match a description, best matches first. Hand the ids to share_photos to show them."""
    body: dict[str, Any] = {"query": query, "size": limit}
    if taken_after:
        body["takenAfter"] = f"{taken_after}T00:00:00.000Z"
    if taken_before:
        body["takenBefore"] = f"{taken_before}T23:59:59.999Z"
    r = await _post("/search/smart", body)
    return [_asset(a) for a in (r.get("assets") or {}).get("items") or []]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def photos_between(
    from_date: str = Field(..., description="YYYY-MM-DD"),
    to_date: str = Field(..., description="YYYY-MM-DD"),
    limit: int = Field(30, ge=1, le=100),
) -> dict:
    """What was photographed in a date range: the count and a sample, newest first."""
    body = {"takenAfter": f"{from_date}T00:00:00.000Z", "takenBefore": f"{to_date}T23:59:59.999Z", "size": limit, "order": "desc"}
    r = await _post("/search/metadata", body)
    assets = r.get("assets") or {}
    return {"total": assets.get("total"), "items": [_asset(a) for a in assets.get("items") or []]}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def photos_on_this_day() -> list[dict]:
    """Immich's memories for today: what was photographed on this date in earlier years."""
    today = date.today()
    memories = await _get("/memories", **{"for": f"{today.isoformat()}T12:00:00.000Z"})
    out = []
    for m in memories:
        years = (m.get("data") or {}).get("year")
        out.append({"year": years, "assets": [_asset(a) for a in (m.get("assets") or [])[:10]], "count": len(m.get("assets") or [])})
    return sorted(out, key=lambda x: x["year"] or 0)


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_albums() -> list[dict]:
    """Albums with their size and date range."""
    albums = await _get("/albums")
    return [
        {"id": a["id"], "name": a.get("albumName"), "assets": a.get("assetCount"), "from": (a.get("startDate") or "")[:10], "to": (a.get("endDate") or "")[:10]}
        for a in albums
    ]


# --- write tools -----------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def share_photos(
    asset_ids: list[str] = Field(..., description="Asset ids from search_photos, photos_between or photos_on_this_day (at most 50)."),
    expires_in_days: int = Field(7, ge=1, le=90),
    description: str = "",
) -> dict:
    """Make a shared link for these photos that opens without a login, and return its URL."""
    if not asset_ids or len(asset_ids) > 50:
        raise RuntimeError("give between 1 and 50 asset ids")
    expires = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat().replace("+00:00", "Z")
    r = await _post(
        "/shared-links",
        {"type": "INDIVIDUAL", "assetIds": asset_ids, "expiresAt": expires, "allowDownload": True, "showMetadata": True, "description": description or None},
    )
    key = r.get("key")
    return {"url": f"{PUBLIC_URL}/share/{key}" if PUBLIC_URL and key else None, "key": key, "expires": expires[:10], "assets": len(asset_ids)}
