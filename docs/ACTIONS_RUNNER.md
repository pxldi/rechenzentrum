# Self-Hosted Actions Runner

CI for the `pxldi-labs` org runs on this cluster instead of GitHub-hosted
runners, so private repos stop drawing down the 2,000 free minutes a month.
Public repos already have unlimited minutes and gain nothing from this.

Deployed by `kubernetes/apps/actions-runner/` — [Actions Runner
Controller](https://github.com/actions/actions-runner-controller) (ARC), the
`gha-runner-scale-set` flavour.

## Using it

```yaml
jobs:
  build:
    runs-on: homelab
```

`homelab` is `runnerScaleSetName` in `helmrelease-runners.yaml`. Runners are
**ephemeral** — a fresh pod per job, destroyed afterwards. Nothing persists
between jobs, including the Docker layer cache, so builds that want caching
must use a registry cache (as `multica-daemon-image.yml` does).

## The image is not `ubuntu-latest`

`ghcr.io/actions/actions-runner` is a bare Ubuntu 24.04 carrying the agent and
almost nothing else. GitHub's hosted image ships tens of gigabytes of
preinstalled tooling; this one has `git`, `curl`, `jq`, `unzip`, `sudo`,
`python3` (with **no** pip) and the `docker` CLI. No node on `PATH` — it exists
only inside the agent's `externals/`, for running JS actions.

So a workflow that worked on `ubuntu-latest` can fail here with **exit 127**,
and the log says only `command not found`. Two patterns cover most of it:

| Symptom                                                                 | Fix                                                              |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------- |
| A composite action shells out to a tool it assumes is installed         | Run the tool as a pinned container instead — dind is right there |
| An action installs a node wrapper (`setup-terraform`, `setup-opentofu`) | Set `terraform_wrapper: false` / `tofu_wrapper: false`           |

Preferring a pinned container over "whatever the runner happens to have" also
fixes a problem the hosted runners always had: their tool versions moved on
every image rebuild, silently.

## Why org-scoped

GitHub only allows **repo-scoped** self-hosted runners on personal accounts —
no account-level runners, no runner groups. One scale set per repo does not
scale, which is why the repos live under an org.

## Layout

| Namespace     | What                                                          |
| ------------- | ------------------------------------------------------------- |
| `arc-systems` | The controller and the listener that polls GitHub             |
| `arc-runners` | Runner pods, the quota, and the egress policy that cages them |

Runner pods execute code from pull requests next to a privileged Docker
daemon, so `arc-runners` carries a NetworkPolicy that permits the public
internet and DNS and nothing else. RFC1918 is blocked, which covers the pod
CIDR, the service CIDR and the house LAN. Treat any change that widens this as
handing PR authors a route to Authentik and the databases.

## Capacity

The node has 30 GiB and no swap, most of it already committed. `maxRunners: 2`,
`minRunners: 0` (nothing runs while idle), and `limits.yaml` caps the namespace
at 9 GiB of burst. Jobs queue rather than overcommit the node. Raising
`maxRunners` means raising the `ResourceQuota` to match — the quota is the
backstop that keeps a runaway build from OOMing Jellyfin.

## Credentials

A GitHub App owned by the org, installed on the org, its App ID, Installation ID
and private key in `secret.yaml` (SOPS). Permissions for an org-scoped scale set:

| Scope        | Permission          | Level          |
| ------------ | ------------------- | -------------- |
| Organization | Self-hosted runners | Read and write |
| Repository   | Actions             | Read           |
| Repository   | Metadata            | Read           |

No webhook is needed — the listener polls. A webhook and the `workflow_job` event
are only required for webhook-driven scaling, which this does not use.

Rotating the key:

```sh
sops kubernetes/apps/actions-runner/secret.yaml
```

## Upgrades

Both HelmReleases pin the same chart version and must move together — ARC does
not support a controller and a scale set on different versions. Renovate raises
one PR per chart; if it splits them, merge as a pair.
