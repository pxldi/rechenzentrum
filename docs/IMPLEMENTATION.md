# Masterplan implementation

The masterplan describes several independently deployable changes. This table
distinguishes implemented configuration from live activation and prerequisites.

| Area | Current state | Remaining work / gate |
| --- | --- | --- |
| Public repo / fresh history | New `pxldi/rechenzentrum`, exported current deployed tree | Reviewed Flux handover |
| Secrets | SOPS ciphertext retained; per-field validation and Gitleaks | Independent key recovery verification |
| Hosted CI / protection | Offline Flux builds, schemas, policies and secret checks | Required checks must pass on each PR |
| Repository layout | App layout retained; namespace and database ownership separated | Avoid resource ownership changes merely for naming |
| Components | Ingress components retained; rollout, DNS, egress and hardening components added | Opt-in rollout/hardening/egress components added; Excalidraw pilot awaits merge |
| Reliability | Existing Recreate workloads retained; Excalidraw rollout/startup pilot added | Per-workload concurrency and capacity checks |
| Flux | Existing dependencies, waits and Helm drift detection | Six database roots gate apps on actual CNPG Ready conditions; handover awaits merge |
| Admission | Existing image/request CEL and namespace PSA | Pod/ephemeral-container CEL checks added in Audit/Warn mode |
| Cantus isolation | Shared PVC dependencies identified | Storage design, restore verification, controlled migration |
| Exposure / edge | Existing TLS and Authentik retained | Exposure inventory generated; awaiting required external-access list |
| Egress | Existing ingress isolation retained | Per-app egress allowances and reachability tests |
| Resources | Existing requests retained | Measured limits/quotas; avoid arbitrary OOM changes |
| Backups | Six CNPG clusters healthy; recent completed backups observed | New isolated restores and data verification |
| Taskfile | Common validation and status tasks | Operational tasks require operator credentials |
| Monitoring | Existing Prometheus/Grafana/Gotify retained | Agent-specific dashboards after deployment |
| Image automation | Flux updates target automation/images; suspension retained | PR branch/workflow implemented; dedicated write and PR credentials still required |
| ZeroClaw | Not deployed | Provider, Telegram identity/token, supported image/config |
| Tandoor MCP | Not deployed | Separate software repo, API token, tests and published image |
| Homelab MCP | Not deployed | Separate software repo, scoped RBAC, tested implementation |
| Agent actions | Existing access documented | Separate diagnostic/action identities and action authorization |

Never mark a restore tested, a service deployed or a policy enforced solely
because its manifests build successfully.
