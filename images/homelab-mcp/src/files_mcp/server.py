"""Tools over the files people send the bot.

ZeroClaw saves a Telegram attachment under its workspace (telegram_files/)
and only writes the path into the prompt; the model has no file tool. This
server runs as a sidecar in the ZeroClaw pod on the same volume and turns
such a file into text, into a page picture, or into a Paperless document.
Every path must resolve under FILES_ROOT; nothing here writes to it.
"""

import os
from datetime import datetime
from pathlib import Path

import httpx
import pymupdf
from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from pydantic import Field

from serve import guarded

mcp = MCPServer("files")

ROOT = Path(os.environ.get("FILES_ROOT", "/workspace")).resolve()
MAX_BYTES = 20 * 1024 * 1024
DOC_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif", ".bmp"}
PAPERLESS_URL = os.environ.get("PAPERLESS_URL", "").rstrip("/")
PAPERLESS_TOKEN = os.environ.get("PAPERLESS_TOKEN", "")


def _resolve(path: str) -> Path:
    raw = path.strip()
    p = Path(raw)
    p = (p if p.is_absolute() else ROOT / raw).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise RuntimeError(f"{raw!r} is outside the bot's file area")
    if not p.is_file():
        raise RuntimeError(f"no file at {raw!r}; see list_received_files")
    if p.stat().st_size > MAX_BYTES:
        raise RuntimeError("file is larger than 20 MB")
    return p


def _open(p: Path) -> pymupdf.Document:
    if p.suffix.lower() == ".pdf":
        return pymupdf.open(p)
    if p.suffix.lower() in DOC_TYPES:
        # An image becomes a one-page document, so the same page tools apply.
        img = pymupdf.open(p)
        pdf = pymupdf.open("pdf", img.convert_to_pdf())
        return pdf
    raise RuntimeError(f"{p.name}: only PDF and image files are supported")


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(RuntimeError, OSError)
def list_received_files(limit: int = Field(15, ge=1, le=100)) -> list[dict]:
    """Files the person sent in the chat, newest first, with the path the other tools take."""
    files = [p for p in ROOT.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.relative_to(ROOT).parts)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {"path": str(p), "name": p.name, "kb": p.stat().st_size // 1024, "received": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")}
        for p in files[:limit]
    ]


@mcp.tool()
@guarded(RuntimeError, OSError, ValueError)
def read_pdf_text(
    path: str = Field(..., description="Path of a received PDF, as ZeroClaw wrote it into the prompt."),
    max_chars: int = Field(8000, ge=200, le=60000),
) -> dict:
    """The text layer of a PDF, page by page. Empty pages are scans: use render_page and look at them."""
    p = _resolve(path)
    doc = _open(p)
    pages = []
    total = 0
    for i, page in enumerate(doc, 1):
        text = " ".join(page.get_text().split())
        if total + len(text) > max_chars:
            text = text[: max(0, max_chars - total)]
        pages.append({"page": i, "chars": len(text), "text": text})
        total += len(text)
        if total >= max_chars:
            break
    return {"name": p.name, "pages": len(doc), "text_pages": pages, "truncated": total >= max_chars, "has_text_layer": any(pg["chars"] > 20 for pg in pages)}


@mcp.tool()
@guarded(RuntimeError, OSError, ValueError)
def render_page(
    path: str = Field(..., description="Path of a received PDF or image."),
    page: int = Field(1, ge=1),
    dpi: int = Field(120, ge=60, le=250, description="120 reads fine; 200 or more for small print."),
) -> Image:
    """One page as a picture (JPEG), to read a scan, a table, a stamp or a chart that has no text layer."""
    p = _resolve(path)
    doc = _open(p)
    if page > len(doc):
        raise RuntimeError(f"{p.name} has {len(doc)} page(s)")
    pix = doc[page - 1].get_pixmap(dpi=dpi)
    return Image(data=pix.tobytes("jpeg"), format="jpeg")


# --- write tools -----------------------------------------------------------


@mcp.tool()
@guarded(httpx.HTTPError, RuntimeError, OSError)
async def send_to_paperless(
    path: str = Field(..., description="Path of a received PDF or image."),
    title: str = Field("", description="Document title; empty keeps the file name."),
) -> dict:
    """Upload a received file to Paperless. It lands in the inbox after OCR; tags and correspondent can be set afterwards with the paperless tools."""
    if not PAPERLESS_URL or not PAPERLESS_TOKEN:
        raise RuntimeError("Paperless is not configured for this server")
    p = _resolve(path)
    data = {"title": title} if title else {}
    async with httpx.AsyncClient(base_url=f"{PAPERLESS_URL}/api", headers={"Authorization": f"Token {PAPERLESS_TOKEN}"}, timeout=60.0) as c:
        with p.open("rb") as fh:
            r = await c.post("/documents/post_document/", data=data, files={"document": (p.name, fh)})
        if r.status_code >= 400:
            raise RuntimeError(f"Paperless answered {r.status_code}: {r.text[:300]}")
    return {"uploaded": p.name, "title": title or p.name, "task": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:80], "note": "consumption takes a minute; the document then shows up in list_documents"}
