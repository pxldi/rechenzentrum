"""Bookmark tools over the Karakeep REST API (Bearer API key)."""

import os
from typing import Any

import httpx
from mcp.server import MCPServer
from pydantic import Field

from serve import guarded

mcp = MCPServer("karakeep")

BASE_URL = os.environ.get("KARAKEEP_URL", "http://karakeep.karakeep.svc.cluster.local:3000").rstrip("/")
PUBLIC_URL = os.environ.get("KARAKEEP_PUBLIC_URL", "").rstrip("/")
KEY = os.environ.get("KARAKEEP_API_KEY", "")


def _client() -> httpx.AsyncClient:
    if not KEY:
        raise RuntimeError("KARAKEEP_API_KEY is not set")
    return httpx.AsyncClient(base_url=f"{BASE_URL}/api/v1", headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"}, timeout=30.0)


async def _get(path: str, **params: Any) -> Any:
    async with _client() as c:
        r = await c.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()


async def _send(method: str, path: str, body: dict) -> Any:
    async with _client() as c:
        r = await c.request(method, path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Karakeep answered {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else {}


def _bookmark(b: dict) -> dict:
    content = b.get("content") or {}
    return {
        "id": b["id"],
        "title": b.get("title") or content.get("title") or content.get("text", "")[:80],
        "url": content.get("url"),
        "type": content.get("type"),
        "created": (b.get("createdAt") or "")[:10],
        "tags": [t.get("name") for t in b.get("tags") or []],
        "note": b.get("note") or None,
        "summary": (b.get("summary") or content.get("description") or "")[:240] or None,
        "archived": b.get("archived"),
        "link": f"{PUBLIC_URL}/dashboard/preview/{b['id']}" if PUBLIC_URL else None,
    }


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def search_bookmarks(query: str = Field(..., description="Full-text over titles, page text and tags. Karakeep's query syntax works, e.g. '#rezept sourdough'."), limit: int = Field(10, ge=1, le=50)) -> list[dict]:
    """Find saved links by text."""
    r = await _get("/bookmarks/search", q=query, limit=limit)
    return [_bookmark(b) for b in r.get("bookmarks") or []]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_bookmarks(limit: int = Field(15, ge=1, le=50), archived: bool = False) -> list[dict]:
    """The most recently saved links."""
    r = await _get("/bookmarks", limit=limit, archived=str(archived).lower())
    return [_bookmark(b) for b in r.get("bookmarks") or []]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def get_bookmark(bookmark_id: str) -> dict:
    """One saved link with its note, tags and (the start of) the page text Karakeep extracted."""
    b = await _get(f"/bookmarks/{bookmark_id}", includeContent="true")
    out = _bookmark(b)
    content = b.get("content") or {}
    out["text"] = (content.get("htmlContent") or content.get("text") or "")[:4000]
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_lists() -> list[dict]:
    """The bookmark lists (folders)."""
    r = await _get("/lists")
    return [{"id": l["id"], "name": l.get("name"), "icon": l.get("icon")} for l in r.get("lists") or []]


# --- write tools -----------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def save_bookmark(
    url: str,
    note: str = "",
    tags: list[str] = Field(default_factory=list, description="Tag names; created if new."),
) -> dict:
    """Save a link. Karakeep fetches the page, its title and a summary on its own afterwards."""
    b = await _send("POST", "/bookmarks", {"type": "link", "url": url, "note": note or None})
    if tags:
        await _send("POST", f"/bookmarks/{b['id']}/tags", {"tags": [{"tagName": t} for t in tags]})
    return _bookmark(await _get(f"/bookmarks/{b['id']}"))
