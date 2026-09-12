# Workflow

Work on a branch, use Conventional Commits, open a PR, wait for all required CI,
and squash-merge. Agents may merge their own authorized work. Human approval is
optional unless the user asks for it; required checks and branch protection stay.

After merging into the active GitOps source, verify Flux, Helm releases, affected
workloads and PVC bindings. Fix or safely revert regressions within the
authorized task.

Public CI runs on GitHub-hosted runners with no decryption key or cluster access.
OpenTofu validation runs on PRs without backend credentials. Operational apply,
notifications, image publication and scheduled flake updates are disabled until
explicitly configured; see `VALIDATION.md`.

Renovate's actual schedule and merge behavior are defined in `renovate.json`.
Image updates must pass the same PR checks as other changes. Major application,
database and host upgrades require compatibility and recovery validation.
