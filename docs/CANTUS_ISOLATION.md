# Cantus namespace isolation

Goal: run Cantus and its database in a `cantus` namespace with baseline Pod
Security, out of `media`, which is `privileged` because of slskd's gluetun
sidecar. Both restores it depends on are verified (see [BACKUPS.md](BACKUPS.md)).

## What is shared today

| Volume | PV directory | Mounted by | Reclaim |
| --- | --- | --- | --- |
| `downloads-pvc` (500Gi, hdd2) | `/mnt/hdd2/openebs/pvc-a9c8f61f-…` | cantus, slskd, sabnzbd, radarr, sonarr | Delete |
| `cantus-music-pvc` (500Gi, hdd1) | `/mnt/hdd1/openebs/pvc-e9719f98-…` | cantus, navidrome, slskd | Delete |
| `cantus-uploads-pvc` (50Gi, hdd1) | `/mnt/hdd1/openebs/pvc-a93a4df8-…` | cantus only | Delete |

None of the three is in any Velero backup. The music library is 5.8 TB on the
hdd1 filesystem. A PVC cannot be referenced from another namespace, and every
PV above is `reclaimPolicy: Delete`, so deleting the PVC object deletes the
directory.

The database `cantus-postgresql` lives in `media` under the `database-cantus`
Flux owner. Cantus reads its URL from the CNPG-generated `cantus-postgresql-app`
secret, which only exists in the database's namespace.

## Options

**A. Leave Cantus in `media`.** Nothing to do. Cantus keeps running under a
privileged namespace. The audit log records violations, so a new privileged
workload is visible. Cheapest; the isolation goal stays unmet.

**B. Move Cantus and bind the shared directories a second time.** Static PVs in
the `cantus` namespace point at the same three directories with
`reclaimPolicy: Retain` and a node affinity. slskd, navidrome and the arr apps
keep their existing claims. Two PV objects per directory is unusual but works
on a single node with OpenEBS local volumes, which are plain directories with no
exclusive lock. The risk is the existing `Delete` policy on the originals: it
must be flipped to `Retain` before any manifest moves.

**C. Move the whole media stack apart from slskd.** slskd is the only reason
`media` is privileged. Moving it into its own namespace needs the same
double-bound volumes as B, for two directories instead of three, and touches
one app instead of Cantus plus its database. Cantus stays where it is, and
`media` drops to baseline.

**D. Give Cantus private copies.** Cantus gets its own music and downloads
directories; slskd downloads into Cantus's inbox through a shared volume anyway.
That shared volume has the same cross-namespace problem, and navidrome must
read the library Cantus writes. This reduces to B with more disk.

## Recommendation: C, then reconsider B

The goal is to get workloads out from under `privileged`. Moving slskd achieves
that for every app in `media` at once, with a smaller blast radius than moving
Cantus, and without touching a database. Cantus only needs to move afterwards
if there is a reason beyond Pod Security, and today there is none.

If Cantus does move later, follow the same volume mechanism and add a database
step: scale Cantus to zero, force a WAL switch, recover into the new namespace
with `targetTime` set after the switch (the verified procedure), and point the
new Deployment at the new `cantus-postgresql-app` secret.

## Plan for slskd

Done 2026-09-13 (PR #16 and the follow-up that set `media` to baseline). The
old config PV object was deleted after the new pod was healthy; the two shared
PVs keep their media claims. Kept for the record and for a future Cantus move.


1. **Retain first.** Patch the live PVs for `downloads-pvc`,
   `cantus-music-pvc` and `slskd-config-pvc` to
   `persistentVolumeReclaimPolicy: Retain`. Live-only change; OpenEBS
   provisioned PVs are not in git. Without this, step 5 deletes the
   directories. Done 2026-09-13 for all three.
2. **Namespace.** Add `kubernetes/namespaces/slskd.yaml` with `enforce:
   privileged` for the gluetun sidecar, and `media` moves to `baseline`. Add the
   ingress policies the media apps need from slskd, and the reverse.
3. **Static volumes.** In `kubernetes/apps/slskd/`, two PVs named
   `slskd-downloads` and `slskd-music` with `local.path` set to the directories
   above, `storageClassName` matching the originals, `Retain`, and
   `nodeAffinity` on the node name. Two PVCs bind them by `volumeName`. Keep
   the uid/gid conventions in the current slskd and Cantus manifests; the
   files are 568:568 and both sides depend on that.
4. **Move the app.** Copy `kubernetes/apps/media/slskd/` to
   `kubernetes/apps/slskd/` with the namespace changed and the claim names
   swapped. slskd's `config` volume is a normal PVC; it is in the weekly Velero
   backup (its last run was Canceled at 6.6 GB, check that before relying on
   it). Move it the same way, as a static PV to its directory.
5. **Cut over.** One PR removes the old manifests and adds the new. `apps`
   prunes the old Deployment and PVCs; with Retain, the PVs go `Released` and
   the directories stay. Delete the Released PV objects by hand afterwards.
6. **Verify.** slskd connects through gluetun, Cantus still picks up downloads,
   navidrome still scans, the audit log shows no new violations in `media`,
   then set `media` to `enforce: baseline`.
7. **Cleanup.** `kubernetes/namespaces/cantus.yaml` actually defines the
   `media` namespace. Rename it to `media.yaml` in the same PR.

Cantus stores the slskd URL in its own settings table as `http://slskd:5030`.
Rather than change a setting under the running app, an ExternalName Service
named `slskd` stays in `media` and points at `slskd.slskd.svc.cluster.local`,
with a matching ingress allowance from `media` in the new namespace. The alias
can go once the setting names the full address.
