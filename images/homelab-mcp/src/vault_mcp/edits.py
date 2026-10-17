"""Text and path rules for edit_note, move_note and delete_note.

Standard library only, like paths.py, so tests/test_vault_edits.py runs
without the SDK.
"""

from datetime import datetime
from pathlib import Path

from vault_mcp.paths import VaultPathError

# Deleted notes move here, inside the write root, so they stay in the synced
# vault and a later move_note can bring them back. A visible folder rather
# than Obsidian's .trash, which the tools skip and the sync may not carry.
TRASH_DIR = "_trash"


def replace_text(text: str, old: str, new: str, replace_all: bool = False) -> tuple[str, int]:
    """text with old replaced by new, and how many places changed.

    Refuses when old is missing, and when it occurs more than once unless
    replace_all is set: a search string that matches twice is one the caller
    did not mean, and in a long note the wrong match is easy to miss.
    """
    if not old:
        raise VaultPathError("old_text is empty")
    count = text.count(old)
    if count == 0:
        raise VaultPathError("old_text was not found in the note; read_note shows its exact text")
    if count > 1 and not replace_all:
        lines = sorted({text.count("\n", 0, i) + 1 for i in _offsets(text, old)})
        shown = ", ".join(str(n) for n in lines[:10])
        raise VaultPathError(
            f"old_text occurs {count} times (lines {shown}); add surrounding text to make it unique, or set replace_all"
        )
    return text.replace(old, new), count


def _offsets(text: str, old: str) -> list[int]:
    out, i = [], text.find(old)
    while i != -1:
        out.append(i)
        i = text.find(old, i + len(old))
    return out


def trash_path(wroot: Path, p: Path, now: datetime) -> Path:
    """Where delete_note puts p: <write root>/_trash/<date>/<path under the
    write root>, with the time added when that name is already taken."""
    trash = wroot / TRASH_DIR
    if p == trash or trash in p.parents:
        raise VaultPathError("the note is already in the trash; remove it from there by hand")
    rel = p.relative_to(wroot)
    target = trash / now.date().isoformat() / rel
    if target.exists():
        target = target.with_name(f"{target.stem}-{now.strftime('%H%M%S')}{target.suffix}")
    if target.exists():
        raise VaultPathError(f"{target.name!r} is already in the trash")
    return target


def in_trash(wroot: Path | None, p: Path) -> bool:
    if wroot is None:
        return False
    trash = wroot / TRASH_DIR
    return trash in p.parents
