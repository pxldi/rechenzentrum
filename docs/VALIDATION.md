# Validation

Linux amd64 setup:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r scripts/requirements.txt
python3 scripts/install-tools.py
export PATH="$PWD/.tools:$PATH"
```

With Task installed: `task validate` and `task secrets:scan`.
The equivalent CI commands are:

```sh
gitleaks dir . --redact=100 --no-banner
python3 scripts/check-secrets.py
python3 -m unittest discover -s tests
yamllint -c .yamllint.yml kubernetes components .github Taskfile.yml
python3 scripts/build.py
python3 scripts/schema-check.py
python3 scripts/check-policies.py
```

`python3 scripts/verify-preservation.py` compares the build with
`policies/preservation-baseline.json` and runs in CI alongside the commands
above. Every entry is an identity, so a workload that is renamed, moved between
namespaces or dropped fails the check; PVCs and CNPG Clusters additionally carry
a hash of their spec. An intentional change to one of those updates the baseline
in the same PR.

HelmReleases are identity-only. They carried a spec hash until 2026-09-16, which
meant every chart bump had to rewrite the baseline; none ever did, the check
failed on 19 of 20 of them, and because no workflow ran it nobody noticed. The
chart version is pinned in the manifest and reviewed in the PR that changes it.

Builds include Flux patches and check duplicate ownership/dependency cycles.
Schemas cover Kubernetes 1.33 and the installed custom-resource kinds; unknown
kinds fail. No cluster credential or decryption key is needed. Built-in schema
retrieval requires network access.

These checks do not render Helm charts, execute admission CEL or verify live
networking/restores. Required infrastructure CI separately evaluates NixOS and
checks Terraform formatting.

Operational workflows are off until configured with their credentials and flags:
`ENABLE_INFRA_APPLY`, `ENABLE_IMAGE_PUBLISH`, `ENABLE_FLAKE_UPDATES`,
`ENABLE_IMAGE_AUTOMATION`.
