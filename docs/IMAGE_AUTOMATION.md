# Image updates through PRs

Flux pushes to `automation/images`, never `main`. The hosted Image Update PR
workflow opens a PR with a dedicated fine-grained user/App credential so the
normal required PR checks run. It neither checks out nor executes branch code.

The existing automation stays suspended until:

1. A dedicated writable GitRepository source and its SOPS-encrypted credential
   are configured. The public `flux-system` source is intentionally anonymous
   and cannot push. Give the image writer repository contents access only.
2. The PR creator's `IMAGE_AUTOMATION_PR_TOKEN` has access to create PRs in this
   repository; store it as a GitHub Actions secret. Do not use `GITHUB_TOKEN`
   for creating these PRs because it suppresses the resulting PR workflows.
3. Set repository variable `ENABLE_IMAGE_AUTOMATION=true`.
4. Select explicit services and semver constraints, restore their setter markers,
   and update the automation sourceRef before unsuspending it. Keep application
   and database majors manual. Use one updater per image to avoid Flux/Renovate
   competing over the same field.
5. Verify a real update opens a PR and all required checks run before enabling
   any automatic merge behavior. There is no branch-protection bypass.

Cantus currently uses a moving development tag. Its source CI remains in its
own repository; switching to immutable release images is a coordinated change
to that project, not an invented tag in this GitOps repository.

References: [Flux image updates](https://fluxcd.io/flux/guides/image-update/),
[GitHub workflow triggering](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow).
