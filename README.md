# rechenzentrum

[![NixOS](https://img.shields.io/badge/NixOS-5277C3?logo=nixos&logoColor=white)](https://nixos.org)
[![K3s](https://img.shields.io/badge/K3s-FFC61C?logo=k3s&logoColor=black)](https://k3s.io)
[![Flux](https://img.shields.io/badge/Flux-5468FF?logo=flux&logoColor=white)](https://fluxcd.io)
[![Renovate](https://img.shields.io/badge/Renovate-enabled-1A1F6C?logo=renovatebot&logoColor=white)](https://docs.renovatebot.com)

A self-hosted, GitOps-managed homelab running on a single NixOS box.

**Public migration in progress.** This repository starts from a fresh snapshot of
the configuration deployed on 2026-09-12. The live cluster still follows the
private archive source until the reviewed handover in [MIGRATION.md](docs/MIGRATION.md).
See [the masterplan](docs/MASTERPLAN.md) and [implementation status](docs/IMPLEMENTATION.md).

No unencrypted secrets belong in Git. SOPS-encrypted Secret manifests are intentional.
Run `task validate` and `task secrets:scan`; setup is in [VALIDATION.md](docs/VALIDATION.md).

The goal: replace cloud services with locally-hosted alternatives, learn Kubernetes properly, and keep the lights on without paying SaaS rent.

Versions are intentionally absent from this document — Renovate updates them weekly and the manifests are the source of truth. The same goes for per-app inventories: `kubernetes/apps/` *is* the app list.

---

## Architecture

Single-node K3s cluster on NixOS, with GitOps reconciliation via Flux. Storage is local-only (no replication, single host). Backups go off-site to Backblaze B2 via Velero + Kopia.

### Hardware

| Component  | Spec                                          |
| ---------- | --------------------------------------------- |
| CPU        | AMD Ryzen 5 5600G (6c / 12t)                  |
| RAM        | 32 GB DDR4                                    |
| SSD        | 1 TB NVMe (system + fast PVCs)                |
| HDD 1      | 12 TB (media library, music)                  |
| HDD 2      | 12 TB (downloads, replicas)                   |
| Network    | 1 GbE, IPv4 only, Cloudflare-managed DNS      |

### Software stack

| Layer            | Tool                                                    |
| ---------------- | ------------------------------------------------------- |
| OS               | NixOS (flake in `nix/`)                                 |
| Orchestration    | K3s                                                     |
| GitOps           | Flux                                                    |
| Storage          | OpenEBS LocalPV                                         |
| Ingress          | Traefik                                                 |
| TLS              | cert-manager (Let's Encrypt, DNS-01 via Cloudflare)     |
| Auth             | Authentik (SSO + OIDC, managed via OpenTofu)            |
| Databases        | CloudNativePG for shared Postgres                       |
| Backup           | Velero + Kopia → Backblaze B2                           |
| Secrets          | SOPS + age                                              |
| Dependency bot   | Renovate (self-hosted)                                  |

### Storage classes

| Class               | Backing       | Use                            | Default |
| ------------------- | ------------- | ------------------------------ | ------- |
| `local-ssd`         | NVMe          | Databases, app configs         | ✅      |
| `local-hdd1`        | 12 TB HDD     | Media library, music           |         |
| `local-hdd2`        | 12 TB HDD     | Downloads, large mutable data  |         |
| `openebs-hostpath`  | NVMe fallback | Generic                        |         |
| `local-path`        | NVMe          | k3s default (rarely used)      |         |

HDD mounts use `noatime,nodiratime` (fewer writes, lets the disks spin down) and `nofail` (the box boots even with a dead HDD).

---

## Applications

Everything lives under `kubernetes/apps/`, is served at `<app>.pxldi.de` behind Traefik with Let's Encrypt TLS, and most apps sit behind Authentik forward-auth. Roughly by category:

- **Productivity & personal** — Nextcloud (files, calendar, contacts), Paperless-ngx (document archive), Tandoor (recipes), Overleaf (LaTeX), AdventureLog (travel log), SparkyFitness (fitness tracking), Sure (personal finance), Grimmory (book library), Ryot (media tracker), Obsidian LiveSync (CouchDB), n8n (workflow automation)
- **Photos & media** — Immich (photos), Jellyfin (media server, GPU transcoding), Navidrome (music streaming), Sonarr / Radarr / Prowlarr (*arr stack), SABnzbd (Usenet), slskd + Soulsync (Soulseek, VPN-isolated), Seerr (request frontend)
- **Infrastructure & tooling** — Authentik (SSO), Glance (dashboard / home page), Homepage (service launcher), Gotify (push notifications), Searxng (metasearch), Home Assistant (smart home, Matter + Thread via OTBR), Ollama (local LLM inference, internal-only), JDownloader, Uptime Kuma (availability monitoring), Velero UI (backup management), Palworld (game server)

---

## Repository layout

```
rechenzentrum/
├── nix/                        NixOS modules (system, k3s, storage, quiet mode)
├── kubernetes/
│   ├── flux-system/            Flux bootstrap
│   ├── infrastructure/         Storage, auth, backup, db operator, networking
│   ├── infrastructure-config/  Config depending on infra CRDs (issuers, policies)
│   └── apps/                   All workloads
├── terraform/                  Authentik provider config (groups, apps, flows)
├── docs/                       Runbooks and conventions (see below)
└── .github/                    CI workflows + Renovate config
```

Flux watches `kubernetes/`. Anything that lands on `main` reconciles within the configured interval. Authentik changes flow through OpenTofu, applied by GitHub Actions on push.

Further docs:

- [`docs/WORKFLOW.md`](docs/WORKFLOW.md) — branch/commit conventions, PR process, Renovate policy
- [`docs/QUIET_MODE.md`](docs/QUIET_MODE.md) — one-time fan-control setup and HDD spin-down runbook

---

## Operations

<details>
<summary><b>Cluster status & debugging</b></summary>

```bash
# Overview
kubectl get nodes
kubectl get pods -A | grep -vE 'Running|Completed'

# Per-namespace state
kubectl get all -n <ns>
kubectl describe pod <pod> -n <ns>
kubectl logs -n <ns> <pod> --tail 100 -f

# Quick exec
kubectl exec -n <ns> -it <pod> -- sh
```

</details>

<details>
<summary><b>Flux GitOps</b></summary>

```bash
# Status of every Flux-managed resource
flux get all -A

# Force reconcile (after pushing a change)
flux reconcile kustomization apps --with-source
flux reconcile kustomization infrastructure --with-source

# Pause / resume a deployment
flux suspend kustomization <name>
flux resume  kustomization <name>

# Tail controller logs
flux logs --all-namespaces -f
```

</details>

<details>
<summary><b>Secrets (SOPS + age)</b></summary>

```bash
# Edit a secret (auto-decrypt on open, re-encrypt on save)
sops kubernetes/apps/<app>/secret.yaml

# Decrypt to stdout (read-only)
sops -d kubernetes/apps/<app>/secret.yaml

# Re-encrypt after rotating recipients
sops updatekeys kubernetes/apps/<app>/secret.yaml
```

</details>

<details>
<summary><b>NixOS</b></summary>

```bash
# Config changes apply themselves: the node pulls main every day at 04:45
# (nix/modules/autoupgrade.nix). To apply right now instead of waiting:
sudo systemctl start nixos-upgrade.service
# or from a checkout:
sudo nixos-rebuild switch --flake .#rechenzentrum

# Roll back to the previous generation
sudo nixos-rebuild switch --rollback

# Clean up old generations
sudo nix-collect-garbage -d
```

</details>

<details>
<summary><b>Fan / disk health (NixOS host)</b></summary>

```bash
# Fan + temp sensors
watch -n 2 sensors

# HDD spin-down status (see nix/modules/quiet.nix for the configured timeout)
sudo hdparm -C /dev/sda /dev/sdb

# Force spin-down (testing)
sudo hdparm -y /dev/sda
```

</details>

---

## Backup & disaster recovery

Backups are run by Velero with the Kopia uploader, shipped to a Backblaze B2 bucket in `eu-central-003`. Two schedules:

| Schedule                | Cron          | Scope                                               | Retention |
| ----------------------- | ------------- | --------------------------------------------------- | --------- |
| `daily-critical-backup` | `0 2 * * *`   | Hand-picked critical namespaces (auth, ingress, …)  | 30 days   |
| `weekly-full-backup`    | `0 3 * * 0`   | Everything except `kube-*`, `openebs`, `velero`     | 90 days   |

Volume data is captured via Kopia file-system backup (`defaultVolumesToFsBackup: true`). Large, easily re-acquired data (media library, downloads) is excluded.

### Restoring a namespace

```bash
# List available backups
velero backup get

# Restore into a sandbox namespace (recommended for testing)
velero restore create test-$(date +%s) \
  --from-backup <backup-name> \
  --namespace-mappings <src>:<src>-test \
  --include-namespaces <src> \
  --exclude-resources ingressroutes.traefik.io,middlewares.traefik.io,networkpolicies.networking.k8s.io

# Watch progress
velero restore describe <restore-name>
kubectl get pods -n <src>-test -w
```

When restoring in-place, drop `--namespace-mappings` and the original resources will be recreated.

### Known caveats

The restore path is verified to work end-to-end (tested with Nextcloud, Immich/CNPG, and AdventureLog), but two real-world gotchas surfaced during testing:

- **Vanilla Postgres images stall in `Init:0/1`.** Velero injects a `restore-wait` init container running as UID 1000; some upstream Postgres images (e.g. `postgis/postgis:15-3.3`) create the data directory as UID 999 with mode `0700`, which blocks the wait helper from reading its marker file. The data lands on the PVC correctly — the pod just can't proceed. Workaround: mount the PVC into a debug pod and `pg_dumpall` the data, or set a pod-level `securityContext.fsGroup`. Bitnami and CNPG-managed Postgres pods do not have this issue.
- **B2 occasionally drops mid-transfer on large restores.** A 22 GB Immich restore failed once with `unexpected EOF` retries, then succeeded cleanly on the second attempt. Velero marks the run as `PartiallyFailed` and won't auto-retry — you have to recreate the restore. Smaller restores (sub-GB) have not failed.

### Full-cluster disaster recovery

1. Reinstall NixOS from the flake in `nix/`.
2. Bootstrap Flux against this repo.
3. Once Velero is back up, `velero restore create --from-backup <latest-weekly>`.
4. Re-link external secrets (B2 credentials, Cloudflare token, age key) — these live outside the cluster.

---

## Roadmap

Rough direction, not a checklist: Prometheus + Grafana with alerting into Gotify, external-HDD backup automation as a NixOS systemd timer, migrating remaining vanilla Postgres pods to CNPG, and eventually a second node (low-power ARM) with replicated storage.

---

## Notes

- DNS-only Cloudflare (no proxy) for everything — TLS terminates at Traefik with Let's Encrypt DNS-01 challenges.
- Single-node, no quorum, no HA. If the box dies, the off-site backups in B2 are the recovery path.
- Renovate runs every weekend, auto-merges patch/minor updates, opens PRs for majors.
- Built for personal use, not a production reference. Steal anything that's useful.
