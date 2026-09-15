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
* `default-deny-egress`, `allow-dns`, `allow-intra-namespace-egress` and
  `allow-internet-egress`: combine with existing ingress isolation and
  app-specific destination/port allowances in the same PR. DNS selects the
  K3s CoreDNS pods; verify this before deploying on a different cluster.
  `allow-intra-namespace-egress` is required by any app that reaches its own
  database, because `allow-intra-namespace` is ingress-only.
  `allow-internet-egress` excludes the pod and service networks and the private
  ranges by literal CIDR; check them before deploying on a different cluster.
  `allow-egress-to-ingress` selects the Traefik pod on its container port and is
  only for an app that calls another service here by its public hostname; an
  egress rule matches the destination after DNAT, so a Service or node address
  is the wrong thing to write.

Kustomize components patch resources rendered by Kustomize. They do not reach
pods rendered later inside a HelmRelease; use chart values or Helm postRenderers
for those workloads. That limit is about patches. A component whose content is a
NetworkPolicy adds a namespaced object with a pod selector, so it does apply to
Helm-rendered pods in the same namespace; `default-deny-egress` and
`allow-dns` are in that group. See [docs/EGRESS.md](../docs/EGRESS.md).
