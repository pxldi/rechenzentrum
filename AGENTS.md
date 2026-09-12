# AGENTS.md — working on `rechenzentrum`

House rules for any AI agent (OpenClaw, Claude Code, …) making changes in this repo.
Read this before you touch anything.

## What this repo is

A **GitOps-managed** single-node NixOS + K3s homelab. Flux continuously reconciles
`kubernetes/` against the cluster. **Merging to `main` changes the live cluster.**
There is no separate "apply" step — the manifest *is* the deployment.

## The golden rule: PRs only, never merge

1. Never commit to `main`. Never `git push` to `main`. Never merge your own PR.
2. Work on a branch, commit, and open a PR with `gh pr create`. A human reviews and merges.
3. The new public repository requires PRs and successful CI on `main`.
   The initial fresh-history bootstrap is the only initialization exception,
   authorized by the repository owner. Subsequent changes require a reviewed PR.
   Do not merge your own PR. The existing private repository is not modified by
   publishing here. Read `docs/MIGRATION.md` before changing reconciliation sources.
4. Use Conventional Commit messages matching the history: `feat(apps): …`,
   `chore(deps): …`, `fix(<scope>): …`.

## Secrets: SOPS + age

- Secrets are encrypted with [SOPS](https://github.com/getsops/sops) + age. Only the
  `data`/`stringData` fields are encrypted (see `.sops.yaml`).
- To add or edit a secret: `sops kubernetes/apps/<app>/secret.yaml` (edits decrypted,
  re-encrypts on save), or create plaintext then `sops --encrypt --in-place <file>`.
- **Never** commit a plaintext secret. **Never** read, print, move, or commit `age.key`
  (the private key, gitignored). Never alter recipients in `.sops.yaml` unless asked.

## kubectl: read/debug only

Your ServiceAccount can `get/list/watch` most resource types cluster-wide (logs
included) and `exec`/`attach`/`port-forward` into pods in **app namespaces only**.
It **cannot** create/update/delete anything. That is intentional: **you change the
cluster by editing manifests and opening a PR**, not with `kubectl apply/edit/delete`.

Two things you will hit and should not try to work around:

- **Secrets are not readable.** `kubectl get secret -o yaml` will 403. If a task
  needs an existing secret value, ask the operator — do not try to reach it by
  exec'ing into a pod that mounts it.
- **`exec` is namespace-scoped.** It is bound in app namespaces but *not* in
  `home-assistant`, `jellyfin`, or `homepage` (those run privileged or hostPath
  pods, where exec is a route to root on the node), nor in `authentik`, `backup`,
  `velero`, `cnpg`, `networking`, `flux-system`, `kube-system` (credential-bearing).

A 403 in those places is the design working, not a bug to route around. Say what you
were trying to do and ask.

## Adding or changing an app

- One directory per app: `kubernetes/apps/<name>/`. Mirror an existing app —
  `n8n` (Helm via bjw-s `app-template` + Postgres) or `glance`/`gethomepage`
  (raw `Deployment`) are good templates.
- Typical files: `namespace.yaml`, `kustomization.yaml`, a workload
  (`helmrelease.yaml` or `deployment.yaml`), `service.yaml`/`ingress.yaml`, `pvc.yaml`,
  `secret.yaml`, plus the shared networkpolicy `components`.
- Register the app in `kubernetes/apps/kustomization.yaml`.
- Ingress = Traefik `IngressRoute` on host `<app>.pxldi.de`, TLS via cert-manager,
  SSO via the `authentik-forward-auth` middleware (copy the two-route pattern from
  `n8n/ingress.yaml`).
- Storage classes: `local-ssd` (default — DBs, configs), `local-hdd1` (media),
  `local-hdd2` (downloads/large mutable). Databases → CloudNativePG (see `n8n`).

## Before opening a PR

- `kubectl kustomize kubernetes/apps/<name>` must build cleanly (and
  `kubectl kustomize kubernetes/apps` for cross-cutting changes).
- Keep YAML prettier-clean (repo uses Prettier; see `.prettierignore`).
- Pin image tags in manifests — Renovate bumps them weekly, so don't use `latest`.
- Don't touch `kubernetes/flux-system/` or bootstrap wiring unless explicitly asked.

## When in doubt

Anything destructive, irreversible, or outward-facing (deleting data/PVCs, changing
DNS, touching auth/ingress for existing apps, editing another app you weren't asked to)
→ stop and ask the operator in the PR description instead of proceeding.
