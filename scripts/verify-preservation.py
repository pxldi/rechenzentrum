#!/usr/bin/env python3
"""Migration check: preserve baseline workload identities and persistent specs.

Run explicitly during this migration. Future intentional database/chart/storage
changes require review against their own baseline, not silently regenerating it.
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
print('\n'.join(errors) if errors else f'PASS: {len(baseline)} baseline identities preserved; PVC, database and Helm specs unchanged')
sys.exit(bool(errors))
