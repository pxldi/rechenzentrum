"""The weekly restore tests stay pointed at the production backups.

Each recovery Cluster is a file inside a ConfigMap, which Flux applies as text
and Renovate cannot see. These checks fail when it drifts from the production
Cluster it restores: a different image is a different Postgres major, which
refuses the data directory; a different serverName or ObjectStore restores
nothing; a WAL archiver would write into the production backup history.
"""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATABASES = ROOT / "kubernetes/databases"
CASES = {
    # directory: (production cluster file, owner secret file or None if CNPG generated it)
    "tandoor": ("postgres-cluster.yaml", "secret.yaml"),
    "immich": ("immich-cnpg.yaml", "secret.yaml"),
    "cantus": ("postgres-cluster.yaml", None),
}


def load(path):
    return [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]


def one(docs, kind, name=None):
    found = [d for d in docs if d["kind"] == kind and (name is None or d["metadata"]["name"] == name)]
    assert len(found) == 1, (kind, name, len(found))
    return found[0]


class RecoveryClusterMatchesProduction(unittest.TestCase):
    def pairs(self):
        for directory, (cluster_file, secret_file) in CASES.items():
            prod = one(load(DATABASES / directory / cluster_file), "Cluster")
            docs = load(DATABASES / directory / "restore-test.yaml")
            test = yaml.safe_load(one(docs, "ConfigMap", "restore-test-cluster")["data"]["cluster.yaml"])
            cron = one(docs, "CronJob", "restore-test")
            secret = one(load(DATABASES / directory / secret_file), "Secret") if secret_file else None
            yield directory, prod, test, cron, secret

    def test_image_and_preloads_match(self):
        for directory, prod, test, _, _ in self.pairs():
            with self.subTest(directory):
                self.assertEqual(test["spec"]["imageName"], prod["spec"]["imageName"])
                self.assertEqual(test["spec"]["postgresql"]["shared_preload_libraries"],
                                 prod["spec"]["postgresql"]["shared_preload_libraries"])

    def test_reads_the_production_archive(self):
        for directory, prod, test, _, _ in self.pairs():
            with self.subTest(directory):
                archive = prod["spec"]["plugins"][0]["parameters"]
                source = test["spec"]["bootstrap"]["recovery"]["source"]
                external = {c["name"]: c for c in test["spec"]["externalClusters"]}[source]
                self.assertEqual(external["plugin"]["parameters"], {
                    "barmanObjectName": archive["barmanObjectName"],
                    "serverName": archive["serverName"],
                })

    def test_never_archives(self):
        for directory, _, test, _, _ in self.pairs():
            with self.subTest(directory):
                self.assertEqual(test["metadata"]["name"], "restore-test")
                self.assertNotIn("plugins", test["spec"])
                self.assertNotIn("backup", test["spec"])
                self.assertEqual(test["spec"]["instances"], 1)

    def test_owner_and_credentials_are_the_production_ones(self):
        for directory, prod, test, cron, secret in self.pairs():
            with self.subTest(directory):
                recovery = test["spec"]["bootstrap"]["recovery"]
                initdb = prod["spec"]["bootstrap"]["initdb"]
                self.assertEqual((recovery["database"], recovery["owner"]), (initdb["database"], initdb["owner"]))
                expected = initdb["secret"]["name"] if "secret" in initdb else f"{prod['metadata']['name']}-app"
                self.assertEqual(recovery["secret"]["name"], expected)
                if secret is not None:
                    self.assertEqual(secret["metadata"]["name"], expected)
                    self.assertTrue({"username", "password"} <= set(secret["stringData"]))
                pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
                verify = next(c for c in pod["initContainers"] if c["name"] == "verify")
                env = {e["name"]: e for e in verify["env"]}
                self.assertEqual(verify["image"], prod["spec"]["imageName"])
                self.assertEqual(env["DB"]["value"], initdb["database"])
                self.assertEqual(env["LIVE_HOST"]["value"], f"{prod['metadata']['name']}-rw")
                for key in ("PGUSER", "PGPASSWORD"):
                    self.assertEqual(env[key]["valueFrom"]["secretKeyRef"]["name"], expected)

    def test_account_is_not_named_after_the_cluster(self):
        # CNPG rewrites the ServiceAccount, Role and RoleBinding named after a
        # Cluster for its instances; the test's own account must not be them.
        for directory, _, test, cron, _ in self.pairs():
            with self.subTest(directory):
                pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
                self.assertNotEqual(pod["serviceAccountName"], test["metadata"]["name"])

    def test_storage_matches(self):
        for directory, prod, test, _, _ in self.pairs():
            with self.subTest(directory):
                self.assertEqual(test["spec"]["storage"], prod["spec"]["storage"])


class VeleroRestoreGetsANewVolume(unittest.TestCase):
    def test_includes_persistentvolumes(self):
        # Without the PV Velero keeps the claim on the live gotify volume, the
        # claim stays Pending and no PodVolumeRestore is ever made.
        docs = load(ROOT / "kubernetes/infrastructure-config/velero/restore-test.yaml")
        restore = yaml.safe_load(one(docs, "ConfigMap", "restore-test-manifests")["data"]["restore.yaml"])
        self.assertEqual(set(restore["spec"]["includedResources"]),
                         {"pods", "persistentvolumeclaims", "persistentvolumes"})


class MonthlyVolumeRestores(unittest.TestCase):
    VELERO = ROOT / "kubernetes/infrastructure-config/velero"

    def setUp(self):
        self.docs = load(self.VELERO / "restore-test-monthly.yaml")
        manifests = one(self.docs, "ConfigMap", "restore-test-monthly-manifests")["data"]
        self.restores = {k: yaml.safe_load(v) for k, v in manifests.items()}

    def test_each_restore_gets_new_volumes_and_its_own_modifier(self):
        for key, restore in self.restores.items():
            with self.subTest(key):
                spec = restore["spec"]
                self.assertEqual(set(spec["includedResources"]),
                                 {"pods", "persistentvolumeclaims", "persistentvolumes"})
                self.assertTrue(spec["orLabelSelectors"])
                modifier = one(self.docs, "ConfigMap", spec["resourceModifier"]["name"])
                self.assertEqual(modifier["metadata"]["namespace"], "velero")

    def test_cronjob_creates_the_restore_it_cleans_up(self):
        for key, restore in self.restores.items():
            with self.subTest(key):
                cron = one(self.docs, "CronJob", f"restore-test-{key[:-len('.yaml')]}")
                pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
                args = [" ".join(c["args"]) for c in pod["initContainers"] + pod["containers"]]
                name = restore["metadata"]["name"]
                self.assertIn(f"create -f /manifests/{key}", args)
                self.assertTrue(all(name in a for a in args if "restore-name" in a or "restores.velero.io" in a))

    def test_rbac_and_admission_allow_exactly_these_names(self):
        rbac = load(self.VELERO / "restore-test.yaml")
        role = one(rbac, "Role", "velero-restore-test")
        deletable = next(r["resourceNames"] for r in role["rules"] if "resourceNames" in r)
        policy = (ROOT / "kubernetes/infrastructure-config/admission-policies/restore-tests.yaml").read_text()
        for restore in self.restores.values():
            name = restore["metadata"]["name"]
            ns = restore["spec"]["includedNamespaces"][0]
            with self.subTest(name):
                self.assertIn(name, deletable)
                self.assertIn(f"'{name}': '{ns}'", policy)

    def test_check_replaces_the_app_containers(self):
        for doc in self.docs:
            if doc["kind"] != "ConfigMap" or "modifier.yaml" not in doc.get("data", {}):
                continue
            with self.subTest(doc["metadata"]["name"]):
                rules = yaml.safe_load(doc["data"]["modifier.yaml"])["resourceModifierRules"]
                patch = yaml.safe_load(rules[0]["strategicPatches"][0]["patchData"])
                containers = patch["spec"]["containers"]
                kept = [c for c in containers if c.get("$patch") != "delete"]
                self.assertEqual([c["name"] for c in kept], ["check"])
                self.assertIn("@sha256:", kept[0]["image"])
                self.assertIsNone(patch["spec"]["priorityClassName"])

    def test_copy_runs_once_and_ends_before_its_job(self):
        # A copy that restarts or waits forever alerts for days: the first run
        # crashlooped one and left the other in PodInitializing.
        for key, restore in self.restores.items():
            with self.subTest(key):
                modifier = one(self.docs, "ConfigMap", restore["spec"]["resourceModifier"]["name"])
                rules = yaml.safe_load(modifier["data"]["modifier.yaml"])["resourceModifierRules"]
                spec = yaml.safe_load(rules[0]["strategicPatches"][0]["patchData"])["spec"]
                self.assertEqual(spec["restartPolicy"], "Never")
                check = next(c for c in spec["containers"] if c["name"] == "check")
                self.assertNotIn("sleep", check["command"][-1])
                job = one(self.docs, "CronJob", f"restore-test-{key[:-len('.yaml')]}")["spec"]["jobTemplate"]["spec"]
                self.assertLess(spec["activeDeadlineSeconds"], job["activeDeadlineSeconds"])
                wait = next(c for c in job["template"]["spec"]["initContainers"] if c["name"] == "wait-check")
                self.assertIn("--for=jsonpath={.status.phase}=Succeeded", wait["args"])

    def test_failed_restore_ends_the_run_at_once(self):
        # Waiting for phase=Completed sat out the full 5h when the restore
        # ended PartiallyFailed.
        for key in self.restores:
            with self.subTest(key):
                pod = one(self.docs, "CronJob", f"restore-test-{key[:-len('.yaml')]}")["spec"]["jobTemplate"]["spec"]["template"]["spec"]
                steps = {c["name"]: c["args"] for c in pod["initContainers"]}
                names = list(steps)
                self.assertIn("--for=jsonpath={.status.completionTimestamp}", steps["wait-restore"])
                self.assertEqual(names[names.index("wait-restore") + 1], "check-restore")
                self.assertIn("--for=jsonpath={.status.phase}=Completed", steps["check-restore"])

    def test_cleanup_covers_every_monthly_copy(self):
        cron = one(self.docs, "CronJob", "remove-restore-test-copies")
        args = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["args"]
        selector = next(a for a in args if a.startswith("--selector="))
        for restore in self.restores.values():
            self.assertIn(restore["metadata"]["name"], selector)
        self.assertNotIn("gotify", selector)


if __name__ == "__main__":
    unittest.main()
