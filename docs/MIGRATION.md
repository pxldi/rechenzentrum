# Public repository handover

## Baseline

The source export is `pxldi-labs/rechenzentrum` revision
`f4942ce4b5e704c868deb2fb66d90602af74dc92`, confirmed as the applied revision of
all four live Flux Kustomizations on 2026-09-12. The local source checkout was
older, so the export uses fetched `origin/main`, not the local working tree.

The initial public snapshot preserves workload names, namespaces, selectors,
PVC specifications, SOPS recipients, Helm release names and versions. There is
no old Git history. The private repository is retained; do not archive it on
GitHub until all consumers below have moved and the rollback window has closed.

## Required recovery evidence

Before moving persistent workloads, record a successful isolated restore of
their database and files with application-level verification. A CNPG Backup
with phase `completed` proves backup creation, not restorability.

Recover the age private key, B2 access and encryption keys, and host bootstrap
access from the operator's independent recovery store. They must remain
available without the cluster or this workstation. Never put them in this repo.

## Repository-only cutover

1. Finish and merge the public migration PRs selected for this cutover. Review
   rendered differences against the baseline. Keep namespace/storage migrations
   in later changes with their own recovery gates.
2. Confirm `main` protection and successful required CI. Confirm the public root
   `GitRepository/flux-system` points to `https://github.com/pxldi/rechenzentrum`.
   Public read access needs no deploy key. Image writes use a separate identity.
3. First merge a **preparation PR in the private repository** setting only
   `apps.spec.prune: false`. Wait until the live apps Kustomization reports that
   new generation Ready. This is a separate reconciliation boundary, not a
   change bundled with the URL switch.
   Then merge the **handover PR in the private repository**, changing only
   `kubernetes/flux-system/gotk-sync.yaml`: set the public HTTPS URL and remove
   `spec.secretRef` from the GitRepository. Keep names, path and sourceRef.
   The public apps root also keeps pruning disabled while database and namespace
   resources transfer to their new owners. A human reviews and merges both PRs.
4. Observe `flux get sources git -A`, `flux get kustomizations -A`, and
   `flux get helmreleases -A`. Each source/reconciliation must report the public
   revision and Ready. Compare workload and PVC identities before and after.
   Verify all six `database-*` inventories own their resources and `apps` no
   longer lists them, then restore `apps.spec.prune: true` in a separate PR.
   Verify the `namespaces` inventory as well. Its pruning remains disabled
   intentionally: namespace retirement must not cascade-delete workloads or PVCs.
5. Separately migrate the NixOS `system.autoUpgrade.flake` URL. The host currently
   pulls the private repository independently of Flux. Apply through the
   existing host workflow and verify its next upgrade succeeds.
6. Install/configure the Renovate GitHub App for the personal repository before
   changing `RENOVATE_REPOSITORIES`; an organization installation ID does not
   automatically grant access to a personal repository. Configure the new
   repository's operational workflow secrets separately.

Do not bootstrap a second Flux installation or rename the four reconciliation
roots during this cutover. No live apply is required from an agent.

## Rollback

An operator can restore the original GitRepository URL and its existing
`flux-system` secretRef if the public source cannot reconcile. Keep the old
read credential until the handover is verified. Suspend affected reconciliation
before investigating unexpected pruning. A Git revert cannot undo a database
migration, recover deleted PVC contents or reverse an incompatible data write.

## Moving resources between Flux owners

Before a later structural split, disable pruning on the **old owner** and let
that setting reconcile. Move resources to the new owner, verify its Ready state
and inventory, then remove the old references and verify that inventory no
longer contains those resources. Only then restore pruning on the old owner.
Treat Namespace and PVC deletion as a separate operation, never an incidental
result of a directory move. See the [Flux FAQ](https://fluxcd.io/flux/faq/).

## Cantus requires a separate storage decision

Cantus currently mounts `media/cantus-music-pvc`, `media/cantus-uploads-pvc`, and
`media/downloads-pvc`. Other media applications share the music/download data.
PVCs cannot be referenced across namespaces. Copying the Deployment and changing
its namespace would leave it unable to mount its data.

Use a reviewed shared-storage/export design or replace filesystem sharing with
application-level transfer before isolating Cantus. Do not duplicate PVs pointing
at the same host directory or grant broad hostPath access as a shortcut. Restore
its CNPG database into the target namespace under a distinct backup server name,
verify it, quiesce writes for final sync, then switch traffic. Retain old data
until the new instance and rollback procedure are verified.
