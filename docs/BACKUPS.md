# Backups and restores

| Data | Backup path |
| --- | --- |
| Six CNPG databases | Barman Cloud plugin -> B2; base backups and WAL |
| Selected application files | Velero/Kopia -> B2 |
| Daily critical namespaces | `daily-critical-backup`, `0 2 * * *`, 30-day retention |
| Weekly selected cluster resources | `weekly-full-backup`, `0 3 * * 0`, 90-day retention |

Scopes and volume exclusions are defined in `kubernetes/infrastructure-config/velero/`.
Database backup settings live in `kubernetes/databases/`. Large media and scratch
volumes may be excluded; check coverage before assuming a file is recoverable.
Schall excludes all three of its volumes (`music`, `downloads`, `uploads`) through
a pod annotation, so its files have no backup at all. Only its database does.

**Evidence, 2026-09-12:** recent backups for all six CNPG clusters reported
`completed`. A point-in-time restore of `cantus-postgresql` and a Velero file
restore of the gotify volume into an isolated namespace were verified the same
day; see below.

## Weekly automated restore test

Every Wednesday morning (Europe/Berlin) four CronJobs named `restore-test`
restore the newest backups and check what came back. Each run starts by removing
whatever the previous one left, and ends by deleting its copy.

| CronJob | Time | Restores | Passes when |
| --- | --- | --- | --- |
| `tandoor/restore-test` | 10:00 | `tandoor-postgresql`, newest base backup plus all archived WAL | Cluster Ready, same table count as live, at least 90% of live rows, a write reads back |
| `media/restore-test` | 10:15 | `cantus-postgresql`, likewise | likewise |
| `immich/restore-test` | 10:30 | `immich-postgresql`, likewise | likewise |
| `velero-restore-test/restore-test` | 10:45 | gotify's `data` volume from the newest `daily-critical-backup` | Restore `Completed`, PodVolumeRestore `Completed`, gotify Ready on the restored database |

The database tests create a Cluster named `restore-test` in the source
namespace, because that is where the ObjectStore and its B2 credential already
are; copying the credential elsewhere would mean decrypting it. The recovery
Cluster has no `spec.plugins`, so it never archives. The Velero test restores
only gotify's pod and claim into `velero-restore-test`, which has default-deny
networking and no Service or route. Its Restore also includes
`persistentvolumes`: Velero never recreates a file-system-backed PV, but only
when it sees the PV does it clear the claim's `volumeName` and provision a new
volume. Without it the claim stays Pending on the live PV and no data is
restored.

The database tests run as the `restore-test-runner` account, not one named
after the Cluster: CNPG owns the ServiceAccount, Role and RoleBinding named
like each Cluster and rewrites them. Each run waits for the last run's
`restore-test-1` claim to be gone before it creates the new Cluster, since a
Cluster that finds a claim of its instance's name adopts it.

What may be created is held twice: RBAC limits deletes to the test object's
name, and the `restore-tests` admission policy refuses any Cluster or Restore
from the test accounts that is not the test object (a different name, a WAL
archiver, superuser access, another namespace's data). `tests/test_restore_tests.py`
fails when a recovery Cluster drifts from its production image, archive or
credentials, and `scripts/schema-check.py` validates the embedded manifests.

Results reach Gotify through the `restore-tests` PrometheusRule in the velero
namespace: `RestoreTestFailed` when a run has not succeeded five hours after it
started, `RestoreTestStale` after eight days without a success,
`RestoreTestNeverSucceeded`, and `RestoreTestMissing` when a CronJob disappears.
Each resolves on the next successful run. The verify step prints only table,
row and size counts, never row content. To run one now:

```sh
kubectl create job -n <namespace> --from=cronjob/restore-test restore-test-manual
```

This is the routine check. It does not replace the manual procedures below,
which compare against a snapshot taken at a known time and test the app against
the restored database.

## Offline copy

`scripts/b2-offline-copy.sh` mirrors the B2 buckets (`rechenzentrum-backups`,
`rechenzentrum-cnpg`, `rechenzentrum-tf-state`) onto a local disk such as an
external drive, as raw objects. Run it from an operator machine with an rclone
remote holding a read-only B2 application key:

```sh
scripts/b2-offline-copy.sh --init /path/to/drive/b2   # once
scripts/b2-offline-copy.sh /path/to/drive/b2          # each time after
```

Objects that vanish from or change in B2 move to `.replaced/` on the copy and
are pruned after 90 days, so an emptied bucket does not empty the copy. Kopia
data stays encrypted, but CNPG base backups and WAL are only gzipped, so the
drive itself must be encrypted. Restoring from the copy needs the Kopia
repository password, the SOPS age key and the database ObjectStore settings,
none of which are on the drive. Run it outside the nightly backup window.

## Restore acceptance

1. Recover age, B2 and Kopia credentials from storage independent of the cluster.
2. Create an isolated target with default-deny networking and bounded storage.
3. Restore CNPG through the installed Barman plugin. Read the original backup
   `serverName`; use a different archive name for the recovered cluster.
4. Restore app files into new PVCs. Exclude production routes, namespaces,
   scheduled jobs, Flux objects and privileged RBAC from test restores.
5. Allow only required recovery traffic. Start the app against its restored
   database and verify records, representative files and a read/write cycle.
6. Record backup ID/time, recovery point, duration and checks. Keep user data and
   SQL dumps private. Retain production data through the rollback window.

Define RPO/RTO targets before moving stateful workloads. A completed backup or healthy
Postgres process alone is not a successful application restore.

## CNPG restore test

`scripts/restore-test/cnpg-restore.yaml` creates a `restore-test` namespace
with default-deny ingress, an ObjectStore that reads the live backup path, and a
recovery Cluster with no WAL archiver and a `targetTime`. It is applied by hand
and deleted afterwards; Flux does not own it.

1. Capture the live state at a known time: database size, table count and a
   row count per table. Use that time as `targetTime`.
2. Apply the manifest, then the source namespace's `cnpg-b2-credentials` SOPS
   file with the namespace changed to `restore-test`.
3. When the Cluster reports healthy, run the same counts against it and a
   create/insert/select/drop cycle. Confirm `spec.plugins` is empty so nothing
   was archived back.
4. Record the result here and delete the namespace.

| Run | Source | Target time (UTC) | Duration | Result |
| --- | --- | --- | --- | --- |
| 2026-09-12 | cantus-postgresql, base backup 20260912T001500 plus WAL | 21:47:36 | 5 min from apply to healthy | 1264 MB, 68 tables, 1,264,629 rows identical to the live snapshot; read/write cycle passed |

## Velero restore test

Velero's file-system restore only runs for pods it restores itself. It injects a
`restore-wait` init container into the pod, and the node agent writes the volume
before the app container starts. Restoring only the Deployment and PVC produces
an empty volume and a pod that starts fine on it, which looks like success and
is not. Include `pods` and `replicasets`, and check that a PodVolumeRestore
exists and reports `Completed` with the backup's byte count.

```sh
kubectl apply -f scripts/restore-test/velero-namespace.yaml
velero restore create <name> -n velero --from-backup <backup> \
  --include-namespaces <ns> --namespace-mappings <ns>:restore-test \
  --include-resources pods,replicasets,deployments,persistentvolumeclaims,persistentvolumes,serviceaccounts \
  --wait
kubectl get podvolumerestore -n velero -l velero.io/restore-name=<name>
```

Services, routes and NetworkPolicies are left out so the copy cannot take
traffic. Compare file names and sizes with the live pod, confirm the pod turns
Ready on the restored data, then delete the namespace and the restore record.

| Run | Source | Duration | Result |
| --- | --- | --- | --- |
| 2026-09-12 | gotify `data` from `daily-critical-backup-20260912020052` | 21 s submit to Completed, 8 s volume restore | 512000 bytes restored, `gotify.db` same size as live, pod Ready on it |

References: [CNPG](https://cloudnative-pg.io/documentation/current/recovery/),
[Barman plugin](https://cloudnative-pg.io/plugin-barman-cloud/docs/),
[Velero](https://velero.io/docs/main/restore-reference/).

## Schall

Schall audio files are excluded from backup on purpose, decided 2026-09-13.

`cantus-music-pvc` held 59 GB of downloaded audio and `cantus-uploads-pvc` was
empty. Both are reproducible: the tracks are re-downloadable, and
`cantus-postgresql` records which ones exist. That database is covered by the
daily CNPG schedule, its most recent backup completed 2026-09-13, and a
point-in-time restore was verified on 2026-09-12.

Schall keeps no configuration on a volume. Every setting arrives as an
environment variable from `kubernetes/apps/media/schall/deployment.yaml`, and the
only application secret, `cantus-auth`, is sops-encrypted in the repository.

A full loss therefore costs the audio files and nothing else. The database says
what to fetch again. Backing up 59 GB of re-downloadable audio to Backblaze was
judged not worth its cost.

## What is excluded, and why

Back up what is hard to obtain or cannot be reproduced. Anything a download or a
rebuild replaces stays out, and the exclusion is recorded here.

Two mechanisms do this. `backup.velero.io/backup-volumes-excludes` on a pod names
individual volumes. The volume policy in
`kubernetes/infrastructure-config/velero/volume-policy-configmap.yaml` matches on
volume type and on PVC labels, which is preferred because the claim that owns the
data carries the reason alongside it.

| What | Size on 2026-09-13 | Why it is out |
| --- | --- | --- |
| Every `emptyDir` | 88 volumes | Destroyed with the pod; a reboot already wipes them |
| `jellyfin` transcode and cache | 42 GB | Scratch, regenerated on demand |
| `media-pvc`, jellyfin `data` for media | 6.3 TB | Media library, not backup material |
| `ollama-models` | 2.6 GB | Pulled from the registry on demand |
| `soundcloud-music-pvc` | 0.5 GB | Downloaded audio; Navidrome reindexes from the files |
| Schall audio | 59 GB | Re-downloadable, and the database records what exists |
| `slskd-config` | 6.2 GB on 2026-09-15 | Partial downloads, a search cache and transfer history; the configuration is a sops Secret, not on the volume |

To exclude a new claim, add `backup.rechenzentrum.dev/reproducible: "true"` to its
labels and add a row above. Only use it where a loss costs time rather than
information.
