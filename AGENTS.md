# Working on rechenzentrum

This is a single-node NixOS/K3s homelab managed by Flux. Changes merged to the
active GitOps source are live deployment changes. Preserve the existing
applications and persistent data while completing the user's request.

## Authorization and delivery

- Treat the user's request as authorization to complete work within its scope.
  Do not repeatedly ask for approval for implementation, validation, PR creation
  or merging that the user has already authorized.
- Work on a branch, use Conventional Commits, open a descriptive PR, and wait for
  required CI. **Agents may squash-merge their own PRs after required checks pass.**
  A separate human review is not required unless the user requests one.
- Keep branch protection and required checks. Do not bypass failed checks,
  force-push main, or rewrite existing history to get a change merged.
- Carry authorized migrations through deployment verification. Inspect live
  Flux/Helm/workload health and PVC bindings, then fix or safely roll back
  regressions rather than stopping at a merged PR.
- Ask only for genuinely missing information or authorization outside the task,
  such as deleting unrelated data or choosing which personal services may lose
  public access. Explain the concrete decision and continue independent work.

## Preserve deployments and data

- Inspect the current rendered manifests and deployed revision before editing.
  An older local checkout is not an acceptable baseline.
- Keep names, namespaces, selectors, Helm release identities and PVC specs unless
  changing them is an intentional, verified part of the task.
- Before moving resources between Flux owners, disable old-owner pruning and
  verify it has reconciled. Verify new inventories before restoring pruning.
  Namespace deletion is explicit; its dedicated owner intentionally does not prune.
- A namespace move is not a storage migration. Verify restores and shared-volume
  dependencies before moving stateful workloads. Do not fabricate restore results.
- Use RollingUpdate only when concurrent instances, storage access and available
  capacity support it. Retain deliberate Recreate strategies for stateful apps.

## Secrets and access

- SOPS-encrypted Secrets belong in Git; unencrypted secrets do not. Empty optional
  SOPS values may remain empty. Keep existing recipients unless asked to rotate.
- Never print, publish, copy into the public repository, or inspect the raw age
  private key. Use SOPS through the operator's configured decryption mechanism.
- Never put credentials, raw sensitive logs, Terraform state or kubeconfigs in
  commits, PR descriptions, CI artifacts or user-facing output.
- Prefer GitOps for persistent cluster changes. Use narrowly scoped operational
  commands when authorized and permitted by the available RBAC. Do not bypass a
  denied API permission through pod exec, node access or another identity.
- Do not assume a namespace alone is a security boundary. Pod mutation and exec
  can expose its mounted secrets and ServiceAccount privileges.

## Implementation conventions

- Retain the existing modular layout; do not restructure solely for aesthetics.
  App definitions live in `kubernetes/apps/`, namespaces in
  `kubernetes/namespaces/`, and CNPG resources in `kubernetes/databases/`.
- Software belongs in separate repositories; do not add Git submodules.
- Apply components at app boundaries. Metadata labels must not silently change
  selectors or pod templates. Helm-generated pods need chart values/postRenderers.
- Use explicit image versions/digests. Updates flow through PRs and required CI.
- Public PR workflows run on GitHub-hosted runners without cluster credentials.
  Never execute public PR code on the internal ARC runners.

## Validation

- Use `task validate` and `task secrets:scan` when available, or their underlying
  commands documented in `docs/VALIDATION.md`.
- Build Flux roots including patches, validate Kubernetes and custom-resource
  schemas, check Secret fields and scan the current tree with Gitleaks.
- `python3 scripts/verify-preservation.py` checks workload identities and PVC,
  database and Helm specs against `policies/preservation-baseline.json`. Update
  the baseline in the same PR as an intentional change to one of those specs.
- Test meaningful failure cases for security-sensitive checks. Do not describe
  static validation as proof of live health, policy enforcement or recovery.
- Report what was merged, what reconciled, and any specific unfinished gates.
