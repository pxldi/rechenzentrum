# Implementation status

Status as of 2026-09-12. Configured does not mean live or restore-tested.

| Area | Status |
| --- | --- |
| Public repository | Created with fresh history; bootstrap CI passed |
| Protection | Required PR/CI, no force pushes; agents may merge authorized work |
| Validation | Flux builds, schemas, policy/secret checks and preservation baseline |
| GitOps handover | In progress; old source still active until verified cutover |
| Databases | Six readiness gates configured; database/PVC specs preserved |
| Namespaces | Separate owner configured; namespace deletion remains explicit |
| Components/labels | Metadata-only app labels; opt-in rollout, hardening, DNS/egress |
| Rollout pilot | Excalidraw startup probe and zero-unavailable rolling update configured |
| Admission | Existing policies retained; additional Pod checks in Audit/Warn |
| Exposure | Inventory recorded; internet/VPN choices still needed |
| Backups | Recent CNPG backups completed; no new restore test |
| Image automation | PR workflow configured; writer/PR credentials needed; suspended |
| Cantus namespace | Pending shared-volume design and verified migration |
| NixOS/Renovate | Still target the private repository; separate consumer migration needed |
| Edge/egress expansion | Pending service requirements and reachability tests |
| ZeroClaw/MCP | Not deployed; provider/bot setup, software and scoped credentials needed |

See [MASTERPLAN.md](MASTERPLAN.md) for the remaining scope and
[MIGRATION.md](MIGRATION.md) for handover/rollback steps.
