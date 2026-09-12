# Public repository handover

Baseline: `pxldi-labs/rechenzentrum@f4942ce4b5e704c868deb2fb66d90602af74dc92`,
confirmed as the live Flux revision on 2026-09-12. Exported without old history
or ignored files. Existing identities, PVC specs, database specs and Helm releases
are recorded in `policies/preservation-baseline.json`.

## Cutover

1. Merge the public implementation after required CI passes.
2. In a separate private-repo PR, set `apps.spec.prune: false`. Wait for the live
   Kustomization to reconcile that generation successfully.
3. Merge a second private-repo PR changing the GitRepository URL to
   `https://github.com/pxldi/rechenzentrum` and removing its `secretRef`.
   Preserve names, paths and sourceRef. Do not install another Flux instance.
4. Verify all public Flux roots, Helm releases, workloads and PVC bindings.
   Confirm database and namespace resources belong to their new inventories.
5. Restore `apps.spec.prune: true` through a public PR after its old inventory no
   longer lists the transferred resources. The `namespaces` owner stays non-pruning.
6. Migrate the independent NixOS auto-upgrade URL and Renovate App installation
   separately. Do not archive the private repository while consumers still use it.

Agents may merge these authorized stages after checks pass. The pruning change
must reconcile before the source switch; do not squash those stages together.

## Rollback

Retain the old source credential during cutover. If the public source fails,
restore the original GitRepository URL and `flux-system` secretRef through an
authorized operator action. Suspend affected reconciliation before investigating
unexpected deletion. A Git revert cannot restore deleted data or undo incompatible
schema writes.

## Stateful changes

Follow [BACKUPS.md](BACKUPS.md) before moving data. Recovery credentials must be
available independently of the cluster.

Cantus mounts `media/cantus-music-pvc`, `media/cantus-uploads-pvc` and shared
`media/downloads-pvc`. Other media apps share this data. PVCs cannot be referenced
across namespaces; changing only `metadata.namespace` would break the deployment.
Resolve sharing, restore the database into an isolated target, quiesce/sync writes,
and verify data before switching traffic. Keep old data through the rollback window.
