# Workflow

## Branch Protection

**Branch:** `main`
- Require pull request before merging ✅
- Restrict deletions ✅
- Block force pushes ✅
- Allowed merge: Squash only ✅

## Branch Naming

```
feat/description    - New features
fix/description     - Bug fixes
chore/description   - Maintenance (deps, cleanup)
docs/description    - Documentation
refactor/description - Code restructuring
```

Examples: `feat/openebs-storage`, `fix/traefik-chart`, `chore/update-deps`

## Commit Messages

```
type(scope): subject

Optional body with details.
```

**Types:** feat, fix, chore, docs, refactor, perf, test, build, ci

**Scopes:** nix, flux, storage, networking, traefik, cert-manager, sops, apps

Examples:
```
feat(storage): add OpenEBS with three storage classes
fix(traefik): update values for chart v39 schema
chore(deps): update Flux to v2.4.0
```

## Pull Request Process

1. Create branch from main
2. Make commits (can be messy)
3. Push to origin
4. Create PR with descriptive title/body
5. Squash and merge
6. Delete branch

## Renovate

- **Schedule:** Every weekend
- **Auto-merge:** Minor and patch versions
- **Manual review:** Major versions
- **Config:** `renovate.json`

## CI/CD

- **OpenTofu:** Auto-applies Authentik changes on main push
- **Plan:** Runs on pull requests for Authentik
