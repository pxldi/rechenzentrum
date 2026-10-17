import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

from vault_mcp import edits  # noqa: E402
from vault_mcp.paths import VaultPathError  # noqa: E402


class ReplaceTextTest(unittest.TestCase):
    def test_replaces_a_unique_passage_and_nothing_else(self):
        text = "# A\n\n- eins\n- zwei\n"
        out, n = edits.replace_text(text, "- zwei", "- drei")
        self.assertEqual((out, n), ("# A\n\n- eins\n- drei\n", 1))

    def test_empty_new_text_removes_the_passage(self):
        self.assertEqual(edits.replace_text("a\nb\nc\n", "b\n", "")[0], "a\nc\n")

    def test_missing_text_is_refused(self):
        with self.assertRaises(VaultPathError) as cm:
            edits.replace_text("abc", "x", "y")
        self.assertIn("not found", str(cm.exception))

    def test_empty_old_text_is_refused(self):
        with self.assertRaises(VaultPathError):
            edits.replace_text("abc", "", "y")

    def test_ambiguous_text_is_refused_with_its_lines(self):
        with self.assertRaises(VaultPathError) as cm:
            edits.replace_text("todo\nok\ntodo\n", "todo", "done")
        self.assertIn("2 times", str(cm.exception))
        self.assertIn("lines 1, 3", str(cm.exception))

    def test_replace_all_changes_every_occurrence(self):
        self.assertEqual(edits.replace_text("todo\ntodo\n", "todo", "done", True), ("done\ndone\n", 2))


class TrashPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wroot = Path(self.tmp.name).resolve() / "ops"
        (self.wroot / "tasks").mkdir(parents=True)
        self.now = datetime(2026, 10, 17, 14, 30, 5)

    def tearDown(self):
        self.tmp.cleanup()

    def test_keeps_the_path_under_a_dated_folder(self):
        p = self.wroot / "tasks" / "x.md"
        self.assertEqual(edits.trash_path(self.wroot, p, self.now), self.wroot / "_trash" / "2026-10-17" / "tasks" / "x.md")

    def test_adds_the_time_when_the_name_is_taken(self):
        taken = self.wroot / "_trash" / "2026-10-17" / "tasks" / "x.md"
        taken.parent.mkdir(parents=True)
        taken.write_text("old")
        got = edits.trash_path(self.wroot, self.wroot / "tasks" / "x.md", self.now)
        self.assertEqual(got.name, "x-143005.md")

    def test_refuses_a_note_already_in_the_trash(self):
        with self.assertRaises(VaultPathError):
            edits.trash_path(self.wroot, self.wroot / "_trash" / "2026-10-17" / "x.md", self.now)

    def test_in_trash(self):
        self.assertTrue(edits.in_trash(self.wroot, self.wroot / "_trash" / "a" / "x.md"))
        self.assertFalse(edits.in_trash(self.wroot, self.wroot / "tasks" / "x.md"))
        self.assertFalse(edits.in_trash(None, self.wroot / "_trash" / "x.md"))


if __name__ == "__main__":
    unittest.main()
