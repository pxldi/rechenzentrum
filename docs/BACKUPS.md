# Backups and restores

| Data | Backup path |
| --- | --- |
| Six CNPG databases | Barman Cloud plugin -> B2; base backup every Sunday, WAL continuously, 30-day recovery window |
| Selected application files | Velero/Kopia -> B2 |
| Five databases outside CNPG (authentik, Nextcloud, Paperless, AdventureLog, Grimmory) | Nightly dump onto a volume Velero backs up daily or weekly, beside the raw data directory |
| Daily critical namespaces | `daily-critical-backup`, `20 2 * * *` (UTC), 30-day retention |
| Weekly selected cluster resources | `weekly-full-backup`, `0 3 * * 0`, 90-day retention |

The daily schedule covers authentik, cert-manager, traefik, nextcloud, immich,
gotify and paperless. Everything else that is not excluded is weekly only.

Kopia maintenance runs once a day per repository (`defaultRepoMaintainFrequency:
24h` in the Velero HelmRelease), and one finished maintenance pod per repository
is kept. Velero copies the default into a BackupRepository only when it creates
one, so changing it later also needs
`kubectl -n velero patch backuprepositories.velero.io <name> --type merge -p '{"spec":{"maintenanceFrequency":"24h0m0s"}}'`
on each existing repository.

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

Every Wednesday (Europe/Berlin) seven CronJobs named `restore-test` and one
named `restore-test-authentik-db` restore the newest backups and check what
came back. Each run starts by removing whatever the previous one left, and ends
by deleting its copy. A failed authentik run keeps its copy until
`remove-restore-test-dump-copies` deletes it on Thursday at 12:00.

| CronJob | Time | Restores | Passes when |
| --- | --- | --- | --- |
| `tandoor/restore-test` | 10:00 | `tandoor-postgresql`, newest base backup plus all archived WAL | Cluster Ready, same table count as live, at least 90% of live rows, a write reads back |
| `media/restore-test` | 10:15 | `cantus-postgresql`, likewise | likewise |
| `immich/restore-test` | 10:30 | `immich-postgresql`, likewise | likewise |
| `planka/restore-test` | 11:00 | `planka-postgresql`, likewise | likewise |
| `forgejo/restore-test` | 11:15 | `forgejo-postgresql`, likewise | likewise |
| `anchor/restore-test` | 11:30 | `anchor-postgresql`, likewise | likewise |
| `velero-restore-test/restore-test` | 10:45 | gotify's `data` volume from the newest `daily-critical-backup` | Restore `Completed`, PodVolumeRestore `Completed`, gotify Ready on the restored database |
| `velero-restore-test/restore-test-authentik-db` | 12:00 | authentik's database volume from the newest `daily-critical-backup`, then its newest dump into an empty Postgres 17 | Restore and PodVolumeRestore `Completed`, a dump from the last 36 hours, `pg_restore` without errors, at least 200 tables, 20 applications, one user and one flow |

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

## Database dumps

Five databases run outside CNPG, so barman does not archive them. Velero's
file-system backup copies their data directories while they run, which is only
crash-consistent. A CronJob next to each writes a logical dump every night
before Velero's 02:20 UTC run:

| CronJob | Time (Europe/Berlin) | Database | Dump lands in | Velero schedule |
| --- | --- | --- | --- | --- |
| `authentik/authentik-db-dump` | 01:00 | `authentik-postgresql` (Postgres 17) | `dumps/` on `data-authentik-postgresql-0` | daily |
| `nextcloud/nextcloud-db-dump` | 01:10 | `nextcloud-postgresql` (Postgres 17) | `dumps/` on `data-nextcloud-postgresql-0` | daily |
| `paperless/paperless-db-dump` | 01:20 | `paperless-postgres` (Postgres 18) | `dumps/` on `paperless-postgres-pvc` | daily |
| `adventurelog/adventurelog-db-dump` | 01:30 | `adventurelog-db` (Postgres 15, PostGIS) | `dumps/` on `adventurelog-db-dumps` | weekly |
| `grimmory/grimmory-db-dump` | 01:40 | `grimmory-mariadb` (MariaDB 11.8) | `dumps/` on `grimmory-mariadb-pvc` | weekly |

Postgres dumps are `pg_dump --format=custom` and are kept only after
`pg_restore --list` reads them. The Grimmory dump is gzipped SQL from
`mariadb-dump --single-transaction` and is kept only when it ends with
mariadb-dump's completion line. Each volume holds the newest three; Velero keeps
the history (30 days daily, 90 days weekly). The dump sits on a volume the
database pod mounts because Velero only backs up volumes of running pods, and
the Job's pod is not running at 02:20. AdventureLog's data volume is the data
directory itself, so its dumps have a volume of their own that the database pod
mounts read-only.

Each Job pings healthchecks.io (`<name>-db-dump` checks, created by
`scripts/healthchecks-setup.sh`) at start and with its exit status, so a failed
or missing night reaches the phone without this node. The raw data directory
stays in the backup.

To restore one, take the dump out of a Velero restore of its volume (or off the
live volume), then:

```sh
pg_restore --dbname=<db> --exit-on-error --single-transaction <db>-<time>.dump
gzip -dc grimmory-<time>.sql.gz | mariadb grimmory
```

Restore into an empty database owned by the app's role, on the same or a newer
major; AdventureLog needs a PostGIS server. `restore-test-authentik-db` does
exactly this every Wednesday for authentik, from B2.

| Run | Source | Duration | Result |
| --- | --- | --- | --- |
| 2026-11-27 | `authentik-20261127T205707Z.dump` (25 MB) in `daily-critical-backup-20261127205751` | 47 s restore, 570 MB volume; under 1 min for the check | 230 tables, 6 users, 29 applications and 16 flows, the same as live; copy deleted |

All five dumps were run by hand the same evening: authentik 25 MB, Nextcloud
7.4 MB, Paperless 1.6 MB, AdventureLog 2.8 MB, Grimmory 68 KB.

## Monthly full volume restore test

The two volumes that hold files nothing else can recreate are restored in full
once a month from the newest `daily-critical-backup`:

| CronJob in `velero-restore-test` | When (Europe/Berlin) | Restores | Passes when |
| --- | --- | --- | --- |
| `restore-test-immich-library` | 1st, 11:00 | immich's photo library (`immich-library-pvc`) | Restore `Completed`, PodVolumeRestore `Completed`, all six `.immich` folder markers present, at least 1000 files, 200 random files read back |
| `restore-test-nextcloud-data` | 2nd, 11:00 | Nextcloud's data and app volumes | Restore and PodVolumeRestores `Completed`, `data/.ncdata` (or the older `.ocdata`) and `config/config.php` present, at least 100 files, 200 random files read back |

Each restores the app's pod and claims into `velero-restore-test`, selected by
label so the database pods beside them stay out. A resource modifier replaces
the pod's containers with a busybox check before the pod is created, so the app
never runs in the test namespace and needs none of its secrets. The check prints
counts only and exits; on a failure its log names what was missing. The copy
pod runs once (`restartPolicy: Never`) and has its own deadline, 7h for immich
and 5h for Nextcloud, so a failed check or a volume restore that never finishes
leaves a Failed pod rather than one that crashloops or waits for days. The Job
deletes the copy, and its volume with it, when the check passes. After a failed
run the copy stays for a day to look at, and `remove-restore-test-copies`
deletes it on the 3rd at 11:00.

A full run downloads the whole volume from B2: about 100 GB for immich and
30 GB for Nextcloud (October 2026). Monthly keeps that well inside B2's free
egress. The copy lands on `local-hdd1` next to the original, so that disk needs
the volume's size free for the run.

`RestoreTestMonthlyFailed`, `RestoreTestMonthlyStale` (33 days),
`RestoreTestMonthlyNeverSucceeded` and `RestoreTestMonthlyMissing` report them,
like the weekly rules. To run one now:

```sh
kubectl create job -n velero-restore-test --from=cronjob/restore-test-immich-library restore-test-immich-library-manual
```


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

## Audiobookshelf

`weekly-full-backup` copies `audiobookshelf-config` (the SQLite database) and
`audiobookshelf-metadata` (covers, caches and the app's own backups). Kopia
reads the database file while the app may be writing it, so the copy that is
known to be consistent is the app's own daily backup: Settings > Backups, which
writes a zip to `/metadata/backups` on the backed-up claim. Turn it on after
the first login. The library is excluded (see below).

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
| `audiobookshelf-library` | empty on 2026-11-27 | Audiobooks are re-obtainable and podcasts re-download; the database and covers on the other two claims are backed up |
| `slskd-config` | 6.2 GB on 2026-09-15 | Partial downloads, a search cache and transfer history; the configuration is a sops Secret, not on the volume |

To exclude a new claim, add `backup.rechenzentrum.dev/reproducible: "true"` to its
labels and add a row above. Only use it where a loss costs time rather than
information.
