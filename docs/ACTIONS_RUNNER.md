# Internal Actions runners

ARC remains deployed for `pxldi-labs`. This public GitOps repository uses
GitHub-hosted runners; public PR code must not run on the homelab runner.

| Setting | Source / value |
| --- | --- |
| Manifests | `kubernetes/apps/actions-runner/` |
| Controller namespace | `arc-systems` |
| Runner namespace | `arc-runners` |
| GitHub scope | `https://github.com/pxldi-labs` |
| Scale set | `homelab` |
| Minimum / maximum runners | 0 / 2 |
| Namespace memory limit | 9 GiB |

Runner jobs are ephemeral and use Docker-in-Docker. The runner image does not
provide the full GitHub-hosted toolchain; install or containerize required tools.
Keep controller and runner chart versions aligned. Review `limits.yaml` and
`networkpolicy.yaml` before changing capacity or connectivity.

The GitHub App credential is SOPS-encrypted in `secret.yaml`. Moving this GitOps
repository does not migrate the App installation or change the organization's
runner scope.
