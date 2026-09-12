# Homelab masterplan

Goal: improve the existing single-cluster homelab incrementally, preserving its
applications and data. Implementation status is tracked in [IMPLEMENTATION.md](IMPLEMENTATION.md).

## Repository and delivery

- Public GitOps monorepo with fresh history; keep the private repository as an archive.
- Separate repositories for Cantus and MCP software; no submodules.
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
- Isolate Cantus in its own namespace after resolving shared media PVCs.
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

Sequence: validated public baseline -> staged Flux handover -> verified recovery
and app isolation -> edge/egress changes -> image automation -> MCP/ChatOps.
