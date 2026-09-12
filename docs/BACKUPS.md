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
Cantus excludes all three of its volumes (`music`, `downloads`, `uploads`) through
a pod annotation, so its files have no backup at all. Only its database does.

**Evidence, 2026-09-12:** recent backups for all six CNPG clusters reported
`completed`. A point-in-time restore of `cantus-postgresql` and a Velero file
restore of the gotify volume into an isolated namespace were verified the same
day; see below.

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
