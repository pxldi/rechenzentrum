# Implementation status

Status as of 2026-09-12. Configured does not mean live or restore-tested.

| Area | Status |
| --- | --- |
| Public repository | Created with fresh history; bootstrap CI passed |
| Protection | Required PR/CI, no force pushes; agents may merge authorized work |
| Validation | Flux builds, schemas, policy/secret checks and preservation baseline |
| GitOps handover | Done 2026-09-12; Flux fetches this repository, all roots Ready, `apps` pruning restored |
| Databases | Six readiness gates configured; database/PVC specs preserved |
| Namespaces | Separate owner configured; namespace deletion remains explicit |
| Components/labels | Metadata-only app labels; opt-in rollout, hardening, DNS/egress |
| Rollout pilot | Excalidraw startup probe and zero-unavailable rolling update configured |
| Admission | Existing policies retained; additional Pod checks in Audit/Warn |
| Exposure | Inventory recorded; internet/VPN choices still needed |
| Backups | Recent CNPG backups completed; no new restore test |
| Image automation | PR workflow configured; writer/PR credentials needed; suspended |
| Cantus namespace | Pending shared-volume design and verified migration |
| NixOS/branding | Auto-upgrade flake and branding git-sync fetch the public repository anonymously; applied by the 04:45 timer and the next branding rollout |
| Renovate | Still targets the private repository; the App must be installed on `pxldi` and the installation id in the secret updated first |
| Edge/egress expansion | Pending service requirements and reachability tests |
| ZeroClaw/MCP | Not deployed; provider/bot setup, software and scoped credentials needed |

See [MASTERPLAN.md](MASTERPLAN.md) for the remaining scope and
[MIGRATION.md](MIGRATION.md) for handover/rollback steps.
