"""Path rules for the vault tools.

Kept free of the MCP and pydantic imports so tests/test_vault_paths.py can
exercise them with the standard library alone, the same split as
tandoor_mcp.leftovers.

Two roots. ROOT is what the tools may read: the whole mirrored vault. The
write root is a subfolder of it, and every write has to land inside that
subfolder. The bot reads Telegram and imported web pages, so anything it can
be talked into writing must stay in its own corner of the vault, away from the
notes other agents load as instructions.
"""

from pathlib import Path


class VaultPathError(RuntimeError):
    """A path that is empty, escapes the root, or is not writable."""


def note_path(root: Path, rel: str) -> Path:
    """The absolute path of a note inside root, or a VaultPathError."""
    rel = rel.strip().lstrip("/")
    if not rel:
        raise VaultPathError("path is empty")
    if not rel.endswith(".md"):
        rel += ".md"
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise VaultPathError(f"{rel!r} is outside the vault")
    return p


def write_root(root: Path, setting: str | None) -> Path | None:
    """Where writes may land, from the VAULT_WRITE_ROOT setting.

    Unset or empty means writes are refused. "." means the whole root.
    Anything else is a subfolder, which must stay inside root.
    """
    if setting is None or not setting.strip():
        return None
    rel = setting.strip().strip("/")
    if rel in ("", "."):
        return root
    p = (root / rel).resolve()
    if root not in p.parents:
        raise VaultPathError(f"VAULT_WRITE_ROOT {setting!r} is outside the vault")
    return p


def check_writable(root: Path, wroot: Path | None, p: Path) -> None:
    """Raise unless p is inside the write root."""
    if wroot is None:
        raise VaultPathError("writes are disabled: VAULT_WRITE_ROOT is not set")
    if p == wroot or wroot in p.parents:
        return
    where = wroot.relative_to(root).as_posix() if wroot != root else "."
    raise VaultPathError(f"{p.relative_to(root).as_posix()!r} is outside the writable folder {where!r}")
