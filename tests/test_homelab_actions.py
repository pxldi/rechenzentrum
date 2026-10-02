import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

from homelab_mcp import actions  # noqa: E402

NOW = datetime(2026, 10, 2, 15, 30, 0, tzinfo=timezone.utc)
SCHEDULE = {
    "metadata": {"name": "daily-critical-backup"},
    "spec": {"schedule": "0 2 * * *", "template": {"includedNamespaces": ["gotify"], "ttl": "720h", "storageLocation": "default"}},
}


class Restart(unittest.TestCase):
    def test_app_pods_may_restart(self):
        actions.check_restartable("media", [{"app": "navidrome"}])

    def test_protected_namespaces_refused(self):
        for ns in ("kube-system", "flux-system", "cnpg-system", "chatops"):
            with self.assertRaises(RuntimeError, msg=ns):
                actions.check_restartable(ns, [{"app": "x"}])

    def test_cnpg_instances_refused(self):
        with self.assertRaises(RuntimeError):
            actions.check_restartable("immich", [{"cnpg.io/cluster": "immich-postgresql"}])

    def test_no_pods_refused(self):
        with self.assertRaises(RuntimeError):
            actions.check_restartable("media", [])


class Reconcile(unittest.TestCase):
    def test_patch_touches_only_the_annotation(self):
        self.assertEqual(
            actions.reconcile_patch(NOW),
            {"metadata": {"annotations": {"reconcile.fluxcd.io/requestedAt": "2026-10-02T15:30:00+00:00"}}},
        )

    def test_kinds(self):
        self.assertEqual(actions.flux_kind("HelmRelease")[2], "helmreleases")
        with self.assertRaises(RuntimeError):
            actions.flux_kind("deployment")


class Backup(unittest.TestCase):
    def test_copies_the_template_verbatim(self):
        body = actions.manual_backup(SCHEDULE, NOW)
        self.assertEqual(body["spec"], SCHEDULE["spec"]["template"])
        self.assertEqual(body["metadata"]["name"], "daily-critical-backup-manual-20261002153000")
        self.assertEqual(body["metadata"]["namespace"], "velero")

    def test_not_counted_as_a_scheduled_run(self):
        labels = actions.manual_backup(SCHEDULE, NOW)["metadata"]["labels"]
        self.assertNotIn("velero.io/schedule-name", labels)

    def test_hooks_refused(self):
        hooked = {"metadata": {"name": "s"}, "spec": {"template": {"hooks": {"resources": [{"name": "x"}]}}}}
        with self.assertRaises(RuntimeError):
            actions.manual_backup(hooked, NOW)

    def test_missing_template_refused(self):
        with self.assertRaises(RuntimeError):
            actions.manual_backup({"metadata": {"name": "s"}, "spec": {}}, NOW)


if __name__ == "__main__":
    unittest.main()
