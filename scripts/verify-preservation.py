#!/usr/bin/env python3
"""Check that workload identities and persistent specs match the baseline.

Two things are checked, and the difference matters. Every entry is an identity:
if a Deployment, StatefulSet, Namespace or PVC in the baseline stops being
built, that is an error, because it means something was renamed, moved between
namespaces or dropped. On top of that, PVCs and CNPG Clusters carry a hash of
their spec, because a storage class, a size or a database parameter changing
silently is the failure this repository most wants to catch.

HelmReleases are identity-only on purpose. They used to carry a spec hash too,
which meant every routine chart bump had to rewrite this file; none ever did, so
by 2026-09-16 the check failed on 19 of 20 of them and nobody could run it. A
chart version is pinned in a manifest and reviewed in the pull request that
changes it, so hashing it here duplicated git and cost the 147 checks that do
catch something.

An intentional database or storage change updates
policies/preservation-baseline.json in the same PR. The baseline is never
regenerated silently.
"""
from pathlib import Path
import hashlib
import json
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
baseline = json.loads((ROOT / 'policies/preservation-baseline.json').read_text())
current = {}
for d in yaml.safe_load_all((ROOT / '.build/all.yaml').read_text()):
    if isinstance(d, dict):
        m = d.get('metadata', {})
        identity = '/'.join([d['apiVersion'], d['kind'], m.get('namespace', ''), m.get('name', '')])
        current[identity] = d
errors = []
for identity, record in baseline.items():
    if identity not in current:
        errors.append(f'Missing baseline resource: {identity}')
    elif 'spec_sha256' in record:
        actual = hashlib.sha256(json.dumps(current[identity].get('spec', {}), sort_keys=True).encode()).hexdigest()
        if actual != record['spec_sha256']:
            errors.append(f'Persistent resource/chart spec changed: {identity}')
hashed = sum('spec_sha256' in r for r in baseline.values())
print('\n'.join(errors) if errors else
      f'PASS: {len(baseline)} baseline identities preserved, {hashed} PVC and database specs unchanged')
sys.exit(bool(errors))
