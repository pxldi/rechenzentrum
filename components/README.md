# Opt-in components

Apply components at an individual app boundary. Existing workloads keep their
identities and selectors; do not use a common-label transformer that changes
selectors across this repository.

* `safe-rollout`: only for applications that support concurrent instances and
  have readiness probes and room for one surge pod. PVC-backed Recreate apps
  do not inherit it. Excalidraw is the first stateless consumer.
* `deployment-hardening`: pod-level defaults merged with existing settings.
  Set container-level `allowPrivilegeEscalation`, capabilities and filesystem
  permissions per image. Do not apply to apps needing the Kubernetes API token
  or images that require root. A component is not an admission boundary.
* `default-deny-egress` and `allow-dns`: combine with existing ingress isolation
  and app-specific destination/port allowances in the same PR. DNS selects the
  K3s CoreDNS pods; verify this before deploying on a different cluster.

Kustomize components patch resources rendered by Kustomize. They do not reach
pods rendered later inside a HelmRelease; use chart values or Helm postRenderers
for those workloads.
