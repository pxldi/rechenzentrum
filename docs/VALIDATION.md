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

For this migration also run `python3 scripts/verify-preservation.py`.

Builds include Flux patches and check duplicate ownership/dependency cycles.
Schemas cover Kubernetes 1.33 and the installed custom-resource kinds; unknown
kinds fail. No cluster credential or decryption key is needed. Built-in schema
retrieval requires network access.

These checks do not render Helm charts, execute admission CEL or verify live
networking/restores. Required infrastructure CI separately evaluates NixOS and
checks Terraform formatting.

Operational workflows are off until configured with their credentials and flags:
`ENABLE_INFRA_APPLY`, `ENABLE_IMAGE_PUBLISH`, `ENABLE_FLAKE_UPDATES`,
`ENABLE_NOTIFICATIONS`, `ENABLE_IMAGE_AUTOMATION`.
