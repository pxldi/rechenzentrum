# rechenzentrum

Single-node NixOS/K3s homelab managed with Flux, Kustomize, Helm and SOPS.

## Layout

| Path | Purpose |
| --- | --- |
| `kubernetes/flux-system/` | Flux controllers and Git source |
| `kubernetes/infrastructure/` | Networking, storage, controllers, monitoring, backups |
| `kubernetes/infrastructure-config/` | Policies and controller-dependent configuration |
| `kubernetes/namespaces/` | App namespaces; explicit deletion only |
| `kubernetes/databases/` | CNPG databases, credentials and backup configuration |
| `kubernetes/apps/` | Application deployments |
| `components/` | Opt-in Kustomize components |
| `nix/` | Host configuration |
| `terraform/authentik/` | Authentik configuration and branding |
| `scripts/`, `Taskfile.yml` | Validation and operations |

Traefik handles ingress, cert-manager issues certificates, and Authentik provides
SSO. OpenEBS local volumes use `local-ssd`, `local-hdd1` and `local-hdd2`.
CNPG backs up PostgreSQL through Barman; Velero/Kopia backs up selected files to B2.
There is no node-level high availability.

## Work on the repo

```sh
task validate
task secrets:scan
task flux:status
```

Tool setup: [VALIDATION.md](docs/VALIDATION.md). Agents may merge authorized PRs
after required CI passes; see [AGENTS.md](AGENTS.md). Merging to the active Flux
source deploys cluster changes. NixOS has a separate auto-upgrade source.

SOPS ciphertext is committed intentionally. Private keys, plaintext secrets,
Terraform state and kubeconfigs are excluded.

## Operations

- [Backups and restore acceptance](docs/BACKUPS.md)
- [Schall isolation design](docs/SCHALL_ISOLATION.md)
- [Exposure inventory](docs/EXPOSURE.md)
- [Rollout inventory](docs/ROLLOUTS.md)
- [Internal Actions runners](docs/ACTIONS_RUNNER.md)
- [ChatOps: the Telegram agent](docs/CHATOPS.md)
- [Host power settings](docs/QUIET_MODE.md)
- [Masterplan and open work](docs/MASTERPLAN.md)
