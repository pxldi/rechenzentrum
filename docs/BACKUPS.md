# Recovery acceptance before stateful migration

Recent CNPG backups for all six databases reported `completed` during the
2026-09-12 inspection. No new restore was executed in this migration session.
Previous README claims of restore testing are historical, not current evidence.

## Independent recovery material

Keep the age private key, B2 credentials, Kopia encryption password, host access
and disk/mount inventory in an operator-controlled recovery store outside this
cluster. Recover those first; Flux cannot decrypt backup credentials without
the age key, and Velero cannot retrieve backups without storage credentials.
GitHub repository secrets do not move with a Git export.

## CNPG database restore

Use the Barman Cloud plugin recovery procedure matching the installed plugin
and CNPG versions. Recover a new Cluster into a dedicated namespace using the
existing ObjectStore backup source and original `serverName`. Give the recovered
cluster a different archive `serverName`, or disable archiving during the test;
never let a test cluster overwrite the source backup history.

The test namespace must start with default-deny ingress/egress. Permit only the
operator, DNS, Kubernetes API where needed, and the backup endpoint. Do not
restore production IngressRoutes, external DNS records, CronJobs, ScheduledBackups,
Flux Kustomizations, privileged RoleBindings or production namespaces into it.
Provision a bounded amount of storage on the intended recovery storage class.

Verify the Cluster Ready condition, connect through operator-controlled access,
and compare application tables/record counts with a recorded reference. Starting
Postgres alone is insufficient. For Tandoor, verify recipes, ingredients and
meal plans; for Cantus, verify library entries and file references.

## File data and application test

Recover Tandoor media and other app files from Velero/Kopia into new claims.
Restore the application against the recovered database, with no public route,
outbound email, scheduled jobs or access to production databases. Verify a
representative media/file download and an application-level read/write cycle.
Do not use a filesystem copy of live PostgreSQL volumes as a substitute for
the database-native backup.

Record: source backup and timestamp, source/target namespace, database recovery
point, recovery duration, record counts, file checks, application version and
result. Keep identifying user data and SQL dumps outside the public repository.
Choose and record RPO/RTO targets with the operator; the existing daily schedule
does not itself establish an acceptable recovery objective.

Keep production data until the migration's rollback window closes. Remove test
namespaces and their claims only after confirming that no retained production
volume is referenced. Namespace deletion is intentionally not automated here.

References: [CNPG recovery](https://cloudnative-pg.io/documentation/current/recovery/),
[Barman Cloud plugin](https://cloudnative-pg.io/plugin-barman-cloud/docs/),
[Velero restore reference](https://velero.io/docs/main/restore-reference/).
