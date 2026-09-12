# Image automation

Flux image automation remains suspended. Its push branch is `automation/images`;
`main` requires a PR and passing CI. Cantus still uses its existing development tag.

To activate selected images:

1. Configure a dedicated writable GitRepository source and SOPS-encrypted
   credential. Anonymous `flux-system` reads cannot push.
2. Set `IMAGE_AUTOMATION_PR_TOKEN` as a GitHub Actions secret and
   `ENABLE_IMAGE_AUTOMATION=true` as a repository variable.
3. Choose semver constraints, restore setter markers, change the automation
   sourceRef and unsuspend it. Avoid overlapping Flux and Renovate ownership.
4. Verify the update PR runs required CI. Do not bypass branch protection.

The PR workflow does not execute branch code. Its dedicated user/App token lets
PR creation trigger CI; creating a PR with `GITHUB_TOKEN` would suppress that event.

Cantus release-image changes belong in its software repository as well.
References: [Flux](https://fluxcd.io/flux/guides/image-update/),
[GitHub events](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow).
