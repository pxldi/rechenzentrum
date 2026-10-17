"""Notes tools over an Obsidian vault.

VAULT_ROOT is the folder the tools read: whatever livesync-bridge mirrors
there, the whole vault in the chatops pod. VAULT_WRITE_ROOT is the one
subfolder the write tools may touch (Clanky/ there); unset, writes are
refused. Every path a tool takes is resolved and has to stay under the root;
only Markdown files are read or written. Nothing here knows about the sync,
so the same server works on any directory. The rules live in paths.py.

With OAUTH_ISSUER set the server asks for an Authentik-issued bearer token on
every /mcp request; that is how the copy claude.ai reaches runs. See oauth.py.
"""

import os
import re
from datetime import date, datetime
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from oauth import server_kwargs
from serve import guarded
from vault_mcp.edits import TRASH_DIR, in_trash, replace_text, trash_path
from vault_mcp.paths import VaultPathError, check_writable, note_path, write_root

mcp = MCPServer("vault", **server_kwargs())

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


def _notes(trash: bool = False) -> list[Path]:
    """Every note, without hidden folders and, unless asked, without the trash."""
    if not ROOT.is_dir():
        return []
    return sorted(
        p
        for p in ROOT.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(ROOT).parts) and (trash or not in_trash(WRITE_ROOT, p))
    )


# --- read tools ------------------------------------------------------------


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def list_notes(folder: str = Field("", description="Subfolder, e.g. 'Clanky/Notizen'. Empty lists everything.")) -> list[dict]:
    """The notes in the vault: path, size and last change. Deleted notes only show when the folder is the trash."""
    base = _resolve(folder + "/x").parent if folder else ROOT
    out = []
    show_trash = WRITE_ROOT is not None and (base == WRITE_ROOT / TRASH_DIR or in_trash(WRITE_ROOT, base))
    for p in _notes(trash=show_trash):
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


MAX_BATCH = 50


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def read_notes(
    paths: list[str] = Field(..., description=f"Up to {MAX_BATCH} note paths relative to the vault."),
) -> list[dict]:
    """Several notes at once. Each entry has the note's text or its own error, so one missing note does not hide the rest."""
    if not paths:
        raise RuntimeError("paths is empty")
    if len(paths) > MAX_BATCH:
        raise RuntimeError(f"at most {MAX_BATCH} paths per call, got {len(paths)}")
    out = []
    for rel in paths:
        try:
            out.append({"ok": True, **read_note(rel)})
        except ToolError as e:
            out.append({"ok": False, "path": rel, "error": str(e)})
    return out


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


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def edit_note(
    path: str = Field(..., description=f"Note path relative to the vault, under '{WRITE_ROOT_REL}/'. Must exist."),
    old_text: str = Field(..., description="Exact text to find, including line breaks and indentation. It must occur once unless replace_all is set."),
    new_text: str = Field(..., description="What replaces it. Empty removes old_text."),
    replace_all: bool = Field(False, description="Replace every occurrence instead of refusing when old_text occurs more than once."),
) -> dict:
    """Replace one passage inside a note in the writable folder and leave the rest as it is.

    Safer than write_note for long notes: nothing outside old_text changes. Fails
    without writing when old_text is missing or ambiguous.
    """
    p = _resolve_writable(path)
    if not p.is_file():
        raise RuntimeError(f"no note at {path!r}; see list_notes")
    try:
        old = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise RuntimeError(f"{path!r} is not valid UTF-8; edit_note would damage it") from e
    text, count = replace_text(old, old_text, new_text, replace_all)
    p.write_text(text, encoding="utf-8")
    return {"path": _rel(p), "replaced": count, "bytes": p.stat().st_size}


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def move_note(
    path: str = Field(..., description=f"The note to move or rename, under '{WRITE_ROOT_REL}/'."),
    to: str = Field(
        ...,
        description=f"New path under '{WRITE_ROOT_REL}/'. Ending in '/' keeps the name and moves the note into that folder, created if new.",
    ),
) -> dict:
    """Move or rename a note inside the writable folder. Refuses to overwrite a note that already exists.

    Also brings a deleted note back: move it out of the trash folder. Links to the
    note are not rewritten; when the name changes, linked_from lists the notes
    whose [[links]] still use the old name.
    """
    src = _resolve_writable(path)
    if not src.is_file():
        raise RuntimeError(f"no note at {path!r}; see list_notes")
    dest = _resolve_writable(to.rstrip() + src.name if to.rstrip().endswith("/") else to)
    if dest == src:
        raise RuntimeError("the note is already there")
    if dest.exists():
        raise RuntimeError(f"{_rel(dest)!r} already exists; pick another name or edit that note")
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)
    out = {"from": _rel(src), "to": _rel(dest)}
    if dest.stem != src.stem:
        out["linked_from"] = _linked_from(src.stem)
    return out


@mcp.tool()
@guarded(VaultPathError, RuntimeError, OSError)
def delete_note(path: str = Field(..., description=f"The note to delete, under '{WRITE_ROOT_REL}/'.")) -> dict:
    """Delete a note in the writable folder by moving it to the trash folder.

    The note keeps its folder structure under <writable folder>/_trash/<date>/, so
    move_note can bring it back. The trash is left out of list_notes and
    search_notes and is emptied by hand. A note that is not there is reported
    as already_removed, not as an error.
    """
    p = _resolve_writable(path)
    if not p.is_file():
        # Deleting twice is harmless: a retry reports the note as gone.
        return {"deleted": _rel(p), "already_removed": True}
    target = trash_path(WRITE_ROOT, p, datetime.now())
    target.parent.mkdir(parents=True, exist_ok=True)
    p.rename(target)
    return {"deleted": _rel(p), "trash": _rel(target)}


def _linked_from(stem: str) -> list[str]:
    pattern = re.compile(r"\[\[(?:[^\]|#]*/)?" + re.escape(stem) + r"(?:\.md)?(?:[#|\]])", re.IGNORECASE)
    out = []
    for p in _notes():
        if pattern.search(p.read_text(encoding="utf-8", errors="replace")):
            out.append(_rel(p))
            if len(out) >= 50:
                break
    return out
