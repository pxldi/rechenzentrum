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


if __name__ == "__main__":
    unittest.main()
