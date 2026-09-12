# Validation

Linux amd64 setup:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r scripts/requirements.txt
python3 scripts/install-tools.py
export PATH="$PWD/.tools:$PATH"
```

Install Task separately, or use the same underlying commands as CI:

```sh
gitleaks dir . --redact=100 --no-banner
python3 scripts/check-secrets.py
yamllint -c .yamllint.yml kubernetes .github Taskfile.yml
python3 scripts/build.py
python3 scripts/schema-check.py
python3 scripts/check-policies.py
```

Builds include Flux patches and recursively follow its local Kustomizations.
Duplicate ownership and dependency cycles fail. No decryption key or cluster
access is required. The schema validator needs network access for built-in
Kubernetes schemas; custom-resource schemas are checked in.

All public PR checks run on disposable GitHub-hosted runners with read-only
repository tokens. The existing ARC deployment remains for its existing users;
no public GitOps workflow selects it.

Runtime policies, Helm-generated pod specifications, external services and data
restores need further validation. A passing static build is not a restore test
or evidence that a NetworkPolicy permits the necessary traffic.

Operational workflows are disabled by default in this new repository. Enable
`ENABLE_INFRA_APPLY`, `ENABLE_IMAGE_PUBLISH`, `ENABLE_FLAKE_UPDATES` or
`ENABLE_NOTIFICATIONS` only after their credentials and targets are configured.
Repository secrets from the old repository are not copied by exporting Git.
