# Homelab masterplan

Goal: improve the existing single-cluster homelab incrementally, preserving its
applications and data.

## Repository and delivery

- Public GitOps monorepo.
- Separate repositories for Schall and MCP software; no submodules.
- GitHub-hosted public CI, required PR checks, and agent-authorized merges.
- YAML, Flux/Kustomize, Kubernetes/CRD schema, policy and secret validation.
- SOPS-encrypted secrets in Git; private keys and plaintext secrets outside it.
- Consistent metadata labels and file naming without gratuitous directory moves.
- Small Taskfile for validation, status, reconciliation and backup workflows.

## Deployment reliability

- Readiness/startup probes and measured resource requests.
- For concurrency-safe apps: `maxUnavailable: 0`, `maxSurge: 1`, `minReadySeconds: 10`.
- Preserve Recreate where storage or application writers require it.
- Flux dependency gates must wait for actual database instances, not only operators.
- Helm drift detection and actionable deployment/Flux alerts.
- Image updates through PRs: selected patches automated; minors opt-in; majors reviewed.
- Reusable rollout, hardening, network-policy and monitoring components where useful.

## Isolation and edge

- Classify services: A public, B internet behind extra authentication, C VPN-only,
  D cluster-internal. Preserve required clients/API routes during changes.
- Default-deny ingress/egress with explicit DNS and application allowances.
- Isolate Schall in its own namespace after resolving shared media PVCs. Schall
  mounts `media/cantus-music-pvc`, `media/cantus-uploads-pvc` and the shared
  `media/downloads-pvc`, which other media apps also use. A PVC cannot be
  referenced across namespaces, so changing only `metadata.namespace` breaks the
  deployment. Resolve the sharing, restore the database into an isolated target,
  quiesce and sync writes, verify the data, then switch traffic. Keep the old
  data through the rollback window.
- Minimum ServiceAccount/RBAC permissions; namespace limits/quotas based on usage.
- CEL/Pod Security rules for images, privileged containers, hostPath and security
  contexts. Introduce new restrictions in Audit/Warn before enforcement.
- Endpoint-specific rate/body/connection limits, timeouts and appropriate headers.
- Evaluate Gateway API without forcing an immediate ingress migration.

## Recovery and monitoring

- Verify database and file restores in isolated targets before stateful migration.
- Keep recovery keys and backup credentials available without the cluster.
- Define recovery objectives, retention and recorded application/data checks.
- Monitor metrics, logs, Flux, deployments and backup freshness/failures.
- Own apps should expose health and metrics endpoints with appropriate access control.

## Later: ChatOps

```text
Telegram -> ZeroClaw -> Tandoor MCP
                    -> Homelab MCP <- coding agents
```

- ZeroClaw handles chat, memory and tool orchestration; no node shell or cluster-admin.
- Keep personal preferences in agent memory/configuration, not MCP business logic.
- Tandoor tools: recipe search/get/create/update and meal-plan list/add.
- Homelab starts read-only: services, deployments, logs, events, Flux and backups.
- Later allowlisted actions: restart a deployment, trigger a backup, reconcile Flux.
- No generic `run_kubectl` tool over Telegram. Use scoped CLI access for coding work.
- Authenticate callers, separate read/action privileges and keep API tokens in MCP services.
- Proactive messages should cover useful failures, with deduplication and rate limits.

Sequence: verified recovery and app isolation -> edge/egress changes -> image
automation -> MCP/ChatOps.

## Status

Configured does not mean live or restore-tested.

| Area | State |
| --- | --- |
| Validation | Flux builds, schemas, policy/secret checks and the preservation baseline run in CI |
| Databases | Six CNPG readiness gates; database and PVC specs preserved |
| Namespaces | Separate Flux owner; namespace deletion stays explicit |
| Components/labels | Metadata-only app labels; opt-in rollout, hardening, DNS/egress components |
| Rollout pilot | Excalidraw has a startup probe and zero-unavailable rolling update |
| Admission | Existing policies retained; additional Pod checks in Audit/Warn |
| Exposure | Decided and applied 2026-09-13: 19 routes require LAN or tailnet plus Authentik, see [EXPOSURE.md](EXPOSURE.md). Karakeep and the Schall API stay public on purpose |
| Backups | CNPG and Velero restores verified 2026-09-12, see [BACKUPS.md](BACKUPS.md); Schall audio files are deliberately excluded, see [BACKUPS.md](BACKUPS.md#cantus) |
| Image automation | PR workflow configured; writer credential needed; suspended |
| Schall namespace | slskd moved out 2026-09-13 and `media` is baseline; Schall stays, see [SCHALL_ISOLATION.md](SCHALL_ISOLATION.md) |
| Edge/egress expansion | Done for every application namespace, see [EGRESS.md](EGRESS.md). `home-assistant` is hostNetwork so policy does not apply; `actions-runner` already had an equivalent rule |
| ZeroClaw/MCP | Not deployed; provider/bot setup, software and scoped credentials needed |
