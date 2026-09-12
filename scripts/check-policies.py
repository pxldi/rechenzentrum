#!/usr/bin/env python3
"""Offline repository guardrails. Runtime CEL/PSA are separate admission checks."""
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
errors = []
docs = [d for d in yaml.safe_load_all((ROOT / ".build/all.yaml").read_text()) if isinstance(d, dict)]
ks = {d['metadata']['name']: d for d in docs if d.get('apiVersion', '').startswith('kustomize.toolkit.fluxcd.io/')}


def walk_dependencies(name, active):
    if name in active:
        errors.append(f"Flux dependency cycle: {' -> '.join([*active, name])}")
        return
    for dep in ks[name].get('spec', {}).get('dependsOn', []):
        if dep['name'] not in ks:
            errors.append(f"{name}: missing dependency {dep['name']}")
        else:
            walk_dependencies(dep['name'], [*active, name])


for name in ks:
    walk_dependencies(name, [])
for doc in docs:
    name = f"{doc.get('kind')}/{doc.get('metadata', {}).get('name')}"
    if doc.get('kind') == 'ImageUpdateAutomation':
        if doc['spec'].get('git', {}).get('push', {}).get('branch') == 'main' and not doc['spec'].get('suspend', False):
            errors.append(f"{name}: active automation must push to a PR branch")
    if doc.get('kind') in ('Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob', 'Pod'):
        spec = doc.get('spec', {})
        if doc['kind'] == 'CronJob':
            spec = spec['jobTemplate']['spec']
        pod = spec if doc['kind'] == 'Pod' else spec['template']['spec']
        for c in pod.get('containers', []) + pod.get('initContainers', []):
            image = c.get('image', '')
            last = image.rsplit('/', 1)[-1]
            if '@sha256:' not in image and (':' not in last or last.endswith(':latest')):
                errors.append(f"{name}/{c['name']}: image needs an explicit tag or digest")
        if doc['kind'] == 'Deployment' and spec.get('strategy', {}).get('rollingUpdate', {}).get('maxUnavailable') == 0:
            if not all(c.get('readinessProbe') for c in pod.get('containers', [])):
                errors.append(f"{name}: zero-unavailable rollout requires container readiness probes")
for path in (ROOT / '.github/workflows').glob('*.yml'):
    workflow = yaml.safe_load(path.read_text())
    for job, value in workflow.get('jobs', {}).items():
        runner = value.get('runs-on', '')
        if not isinstance(runner, str) or not runner.startswith(('ubuntu-', 'windows-', 'macos-')):
            errors.append(f"{path.name}/{job}: must use a GitHub-hosted runner")
    if 'pull_request_target' in workflow.get('on', workflow.get(True, {})):
        errors.append(f"{path.name}: pull_request_target requires explicit security review")
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
for name in tracked:
    parts = Path(name).parts
    if any(p in {'.build', '.tools', '.venv'} for p in parts) or name.endswith(('age.key', '.tfstate')):
        errors.append(f"Forbidden tracked artifact: {name}")
if (ROOT / '.gitmodules').exists():
    errors.append('Submodules are not allowed')
print('\n'.join(errors) if errors else 'PASS: Flux dependencies, image policies, hosted CI, and repository boundaries')
sys.exit(bool(errors))
