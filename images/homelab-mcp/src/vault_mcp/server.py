"""Notes tools over an Obsidian vault.

VAULT_ROOT is the folder the tools read: whatever livesync-bridge mirrors
there, the whole vault in the chatops pod. VAULT_WRITE_ROOT is the one
subfolder the write tools may touch (Clanky/ there); unset, writes are
refused. Every path a tool takes is resolved and has to stay under the root;
only Markdown files are read or written. Nothing here knows about the sync,
so the same server works on any directory. The rules live in paths.py.
"""

import os
import re
from datetime import date
from pathlib import Path

from mcp.server import MCPServer
from pydantic import Field

from serve import guarded
from vault_mcp.paths import VaultPathError, check_writable, note_path, write_root

mcp = MCPServer("vault")

ROOT = Path(os.environ.get("VAULT_ROOT", "/vault")).resolve()
WRITE_ROOT = write_root(ROOT, os.environ.get("VAULT_WRITE_ROOT"))
if WRITE_ROOT is None:
    WRITE_ROOT_REL = "(writes disabled)"
elif WRITE_ROOT == ROOT:
    WRITE_ROOT_REL = "."
else:
    WRITE_ROOT_REL = WRITE_ROOT.relative_to(ROOT).as_posix()
MAX_NOTE_BYTES = 200_000


def _resolve(rel: str) -> Path:
    return note_path(ROOT, rel)


def _resolve_writable(rel: str) -> Path:
    p = note_path(ROOT, rel)
    check_writable(ROOT, WRITE_ROOT, p)
    return p


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def _notes() -> list[Path]:
    if not ROOT.is_dir():
        return []
    return sorted(p for p in ROOT.rglob("*.md") if not any(part.startswith(".") for part in p.relative_to(ROOT).parts))


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def list_notes(folder: str = Field("", description="Subfolder, e.g. 'Clanky/Notizen'. Empty lists everything.")) -> list[dict]:
    """The notes in the vault: path, size and last change."""
    base = _resolve(folder + "/x").parent if folder else ROOT
    out = []
    for p in _notes():
        if base == ROOT or base in p.parents:
            st = p.stat()
            out.append({"path": _rel(p), "bytes": st.st_size, "modified": date.fromtimestamp(st.st_mtime).isoformat()})
    return out


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def read_note(path: str = Field(..., description="Note path relative to the vault, e.g. 'Clanky/Geschmack.md'.")) -> dict:
    """A note's full text."""
    p = _resolve(path)
    if not p.is_file():
        raise RuntimeError(f"no note at {path!r}; see list_notes")
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"path": _rel(p), "text": text[:MAX_NOTE_BYTES], "truncated": len(text) > MAX_NOTE_BYTES}


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def search_notes(query: str = Field(..., description="Case-insensitive text; matching lines are returned with their note.")) -> list[dict]:
    """Lines across all notes that contain the query."""
    q = query.strip().lower()
    if not q:
        raise RuntimeError("query is empty")
    hits = []
    for p in _notes():
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if q in line.lower():
                hits.append({"path": _rel(p), "line": n, "text": line.strip()[:300]})
                if len(hits) >= 100:
                    return hits
    return hits


# --- write tools -----------------------------------------------------------
#
# Writes stay under WRITE_ROOT. The bot reads Telegram and imported pages, and
# the rest of the vault holds notes other agents load as instructions.


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def write_note(
    path: str = Field(..., description=f"Note path relative to the vault, under '{WRITE_ROOT_REL}/'. Created with its folders if new."),
    text: str = Field(..., description="The whole note; replaces what was there."),
) -> dict:
    """Create or replace a note in the writable folder."""
    p = _resolve_writable(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    p.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return {"path": _rel(p), "replaced": existed, "bytes": p.stat().st_size}


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def append_note(
    path: str = Field(..., description=f"Note path relative to the vault, under '{WRITE_ROOT_REL}/'. Created if new."),
    text: str = Field(..., description="Text added at the end, on its own line."),
) -> dict:
    """Add to the end of a note in the writable folder without touching the rest."""
    p = _resolve_writable(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    old = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    sep = "" if not old or old.endswith("\n") else "\n"
    p.write_text(old + sep + text.rstrip("\n") + "\n", encoding="utf-8")
    return {"path": _rel(p), "bytes": p.stat().st_size}


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def log_learned(text: str = Field(..., description="One thing learned today, a sentence or two.")) -> dict:
    """Append to today's note, <writable folder>/Notizen/YYYY-MM-DD.md, creating it with a heading."""
    today = date.today().isoformat()
    p = _resolve_writable(f"{WRITE_ROOT_REL}/Notizen/{today}")
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {today}\n\n", encoding="utf-8")
    bullet = "- " + re.sub(r"\s*\n\s*", " ", text.strip())
    return append_note(_rel(p), bullet)
