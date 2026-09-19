"""Document tools over the Paperless-ngx REST API (token auth)."""

import os
from typing import Any

import httpx
import pymupdf
from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from pydantic import Field

from serve import guarded

mcp = MCPServer("paperless")

BASE_URL = os.environ.get("PAPERLESS_URL", "http://paperless.paperless.svc.cluster.local").rstrip("/")
TOKEN = os.environ.get("PAPERLESS_TOKEN", "")
PUBLIC_URL = os.environ.get("PAPERLESS_PUBLIC_URL", "").rstrip("/")


def _client() -> httpx.AsyncClient:
    if not TOKEN:
        raise RuntimeError("PAPERLESS_TOKEN is not set")
    return httpx.AsyncClient(
        base_url=f"{BASE_URL}/api",
        headers={"Authorization": f"Token {TOKEN}", "Accept": "application/json; version=9"},
        timeout=30.0,
    )


async def _get(path: str, **params: Any) -> Any:
    async with _client() as c:
        r = await c.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()


async def _send(method: str, path: str, body: dict) -> Any:
    async with _client() as c:
        r = await c.request(method, path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Paperless answered {r.status_code}: {r.text[:600]}")
        return r.json() if r.content else {}


async def _names(kind: str) -> dict[int, str]:
    data = await _get(f"/{kind}/", page_size=200)
    return {x["id"]: x["name"] for x in data.get("results", [])}


async def _lookups() -> dict[str, dict[int, str]]:
    return {k: await _names(k) for k in ("correspondents", "document_types", "tags")}


def _summary(d: dict, lk: dict[str, dict[int, str]], snippet: int = 0) -> dict:
    out = {
        "id": d["id"],
        "title": d.get("title"),
        "created": (d.get("created") or "")[:10],
        "added": (d.get("added") or "")[:10],
        "correspondent": lk["correspondents"].get(d.get("correspondent")),
        "document_type": lk["document_types"].get(d.get("document_type")),
        "tags": [lk["tags"].get(t, str(t)) for t in d.get("tags") or []],
        "asn": d.get("archive_serial_number"),
        "url": f"{PUBLIC_URL}/documents/{d['id']}/details" if PUBLIC_URL else None,
    }
    if snippet:
        out["snippet"] = " ".join((d.get("content") or "").split())[:snippet]
    return out


def _id_by_name(table: dict[int, str], name: str, kind: str) -> int:
    wanted = name.strip().lower()
    for i, n in table.items():
        if n.lower() == wanted:
            return i
    raise RuntimeError(f"no {kind} named {name!r}; known: {sorted(table.values())}")


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def search_documents(
    query: str = Field(..., description="Full-text query over titles and OCR text, e.g. 'Rechnung Objektiv' or 'Krankenkasse 2026'."),
    limit: int = Field(10, ge=1, le=50),
) -> list[dict]:
    """Full-text search, best matches first, with a short snippet of each document's text."""
    lk = await _lookups()
    data = await _get("/documents/", query=query, page_size=limit)
    return [_summary(d, lk, snippet=240) for d in data.get("results", [])]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_documents(
    correspondent: str = Field("", description="Filter by correspondent name."),
    document_type: str = Field("", description="Filter by document type name, e.g. 'Rechnung'."),
    tag: str = Field("", description="Filter by tag name."),
    limit: int = Field(20, ge=1, le=100),
) -> list[dict]:
    """Newest documents first, optionally filtered by correspondent, type or tag."""
    lk = await _lookups()
    params: dict[str, Any] = {"ordering": "-created", "page_size": limit}
    if correspondent:
        params["correspondent__id"] = _id_by_name(lk["correspondents"], correspondent, "correspondent")
    if document_type:
        params["document_type__id"] = _id_by_name(lk["document_types"], document_type, "document type")
    if tag:
        params["tags__id__all"] = _id_by_name(lk["tags"], tag, "tag")
    data = await _get("/documents/", **params)
    return [_summary(d, lk) for d in data.get("results", [])]


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def get_document(
    document_id: int,
    max_chars: int = Field(6000, ge=200, le=40000, description="How much of the OCR text to return."),
) -> dict:
    """One document with its metadata and (the start of) its full text."""
    lk = await _lookups()
    d = await _get(f"/documents/{document_id}/")
    out = _summary(d, lk)
    text = d.get("content") or ""
    out["text"] = text[:max_chars]
    out["truncated"] = len(text) > max_chars
    out["notes"] = [n.get("note") for n in d.get("notes") or []]
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def list_labels() -> dict:
    """Every correspondent, document type and tag, with document counts where Paperless reports them."""
    out = {}
    for kind in ("correspondents", "document_types", "tags"):
        data = await _get(f"/{kind}/", page_size=200)
        out[kind] = [{"name": x["name"], "documents": x.get("document_count")} for x in data.get("results", [])]
    return out


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError, ValueError)
async def get_document_page(
    document_id: int,
    page: int = Field(1, ge=1, description="1-based page number."),
    dpi: int = Field(120, ge=60, le=250, description="Render resolution; 120 reads fine, 250 for small print."),
) -> Image:
    """One page of a document as a picture (JPEG), rendered from Paperless's PDF. For
    reading a stamp, a table or a layout the OCR text does not carry, or to show
    the person the scan itself."""
    async with _client() as c:
        r = await c.get(f"/documents/{document_id}/preview/")
        if r.status_code == 404:
            raise RuntimeError(f"no document {document_id}")
        r.raise_for_status()
        pdf = r.content
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    if page > len(doc):
        raise RuntimeError(f"document {document_id} has {len(doc)} page(s)")
    pix = doc[page - 1].get_pixmap(dpi=dpi)
    return Image(data=pix.tobytes("jpeg"), format="jpeg")


# --- write tools -----------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def update_document(
    document_id: int,
    title: str | None = None,
    correspondent: str | None = Field(None, description="Correspondent name; must exist (see list_labels)."),
    document_type: str | None = Field(None, description="Document type name; must exist."),
    tags: list[str] | None = Field(None, description="Replaces the tag list. Names must exist; create_tag first if not."),
) -> dict:
    """Change a document's title, correspondent, type or tags. Only given fields change."""
    lk = await _lookups()
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    if correspondent is not None:
        body["correspondent"] = _id_by_name(lk["correspondents"], correspondent, "correspondent")
    if document_type is not None:
        body["document_type"] = _id_by_name(lk["document_types"], document_type, "document type")
    if tags is not None:
        body["tags"] = [_id_by_name(lk["tags"], t, "tag") for t in tags]
    if not body:
        return {"id": document_id, "changed": []}
    d = await _send("PATCH", f"/documents/{document_id}/", body)
    return {**_summary(d, lk), "changed": sorted(body)}


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError)
async def create_tag(name: str) -> dict:
    """Create a tag (no auto-matching rules)."""
    t = await _send("POST", "/tags/", {"name": name, "matching_algorithm": 0})
    return {"id": t.get("id"), "name": t.get("name")}
