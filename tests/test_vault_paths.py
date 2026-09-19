import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

from vault_mcp import paths  # noqa: E402


class VaultPathsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "Clanky" / "Notizen").mkdir(parents=True)
        (self.root / "ops").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_note_path_adds_extension_and_stays_inside(self):
        p = paths.note_path(self.root, "Clanky/Geschmack")
        self.assertEqual(p, self.root / "Clanky" / "Geschmack.md")
        self.assertEqual(paths.note_path(self.root, "/ops/CLAUDE.md"), self.root / "ops" / "CLAUDE.md")

    def test_note_path_refuses_empty_and_traversal(self):
        with self.assertRaises(paths.VaultPathError):
            paths.note_path(self.root, "   ")
        with self.assertRaises(paths.VaultPathError):
            paths.note_path(self.root, "../outside")
        with self.assertRaises(paths.VaultPathError):
            paths.note_path(self.root, "Clanky/../../etc/passwd")

    def test_write_root_unset_disables_writes(self):
        for setting in (None, "", "  "):
            self.assertIsNone(paths.write_root(self.root, setting))
        with self.assertRaises(paths.VaultPathError) as cm:
            paths.check_writable(self.root, None, self.root / "Clanky" / "x.md")
        self.assertIn("VAULT_WRITE_ROOT", str(cm.exception))

    def test_write_root_dot_is_whole_vault(self):
        wroot = paths.write_root(self.root, ".")
        self.assertEqual(wroot, self.root)
        paths.check_writable(self.root, wroot, self.root / "ops" / "CLAUDE.md")

    def test_write_root_subfolder_allows_only_that_subfolder(self):
        wroot = paths.write_root(self.root, "Clanky/")
        self.assertEqual(wroot, self.root / "Clanky")
        paths.check_writable(self.root, wroot, self.root / "Clanky" / "Geschmack.md")
        paths.check_writable(self.root, wroot, self.root / "Clanky" / "Notizen" / "2026-09-19.md")
        for rel in ("ops/CLAUDE.md", "ops/skills/task/SKILL.md", "ops/tasks/x.md", "Welcome.md", "Clanky.md"):
            with self.assertRaises(paths.VaultPathError, msg=rel):
                paths.check_writable(self.root, wroot, self.root / rel)

    def test_write_root_outside_vault_is_refused(self):
        with self.assertRaises(paths.VaultPathError):
            paths.write_root(self.root, "../elsewhere")


if __name__ == "__main__":
    unittest.main()
