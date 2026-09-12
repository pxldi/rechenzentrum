# Installed custom-resource schemas

These OpenAPI validation schemas were extracted read-only from the running K3s
cluster on 2026-09-12. Only schemas for kinds used by the rendered GitOps roots
are included. No instances, status, credentials or private keys are included.

`scripts/schema-check.py` validates against these schemas and the Kubernetes
1.33 built-in schemas. Unknown kinds fail validation. When upgrading a
controller, update its schema in the same PR from the upstream CRD at the
selected release, then validate the manifests against that version.

JSON Schema validation does not execute Kubernetes CEL validation extensions,
Helm templates, or admission policies. Those require separate checks against
the target API/controller and rendered chart resources.
