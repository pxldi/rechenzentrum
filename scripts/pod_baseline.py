#!/usr/bin/env python3
"""The workload-baseline admission checks, in Python.

The exception lists are read from the policy itself, so this and the
apiserver cannot disagree about which namespace may do what. Used offline by
check-policies.py on the Flux build, and with --live against the running
cluster (read-only: `kubectl get pods -A -o json`).
"""
from pathlib import Path
import json
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "kubernetes/infrastructure-config/admission-policies/workload-baseline.yaml"
EXCLUDED = {"kube-system", "kube-public", "kube-node-lease", "flux-system"}


def load_exceptions(path=POLICY):
    policy = next(d for d in yaml.safe_load_all(path.read_text()) if d and d["kind"] == "ValidatingAdmissionPolicy")
    # Each variable is a CEL list literal of quoted strings, which is also YAML.
    variables = {v["name"]: v["expression"] for v in policy["spec"]["variables"]}
    return {
        "privileged": set(yaml.safe_load(variables["privilegedNamespaces"])),
        "hostPath": set(yaml.safe_load(variables["hostPathNamespaces"])),
        "hostNamespaces": set(yaml.safe_load(variables["hostNamespaceNamespaces"])),
        "capabilities": set(yaml.safe_load(variables["extraCapabilityNamespaces"])),
        "defaultCapabilities": set(yaml.safe_load(variables["defaultCapabilities"])),
    }


def pod_spec(doc):
    kind = doc.get("kind")
    spec = doc.get("spec") or {}
    if kind == "Pod":
        return spec
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"):
        return spec.get("template", {}).get("spec")
    if kind == "CronJob":
        return spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
    return None


def violations(spec, namespace, exceptions):
    """Return what the policy would refuse, as short strings; empty if none."""
    if namespace in EXCLUDED:
        return []
    containers = spec.get("containers", []) + spec.get("initContainers", []) + spec.get("ephemeralContainers", [])
    found = []
    for c in containers:
        sc = c.get("securityContext") or {}
        name = c.get("name", "?")
        if sc.get("privileged") and namespace not in exceptions["privileged"]:
            found.append(f"privileged container {name}")
        added = (sc.get("capabilities") or {}).get("add") or []
        extra = [cap for cap in added if cap not in exceptions["defaultCapabilities"]]
        if extra and namespace not in exceptions["capabilities"]:
            found.append(f"capabilities {','.join(extra)} on {name}")
        host_ports = [p["hostPort"] for p in c.get("ports") or [] if p.get("hostPort")]
        if host_ports and namespace not in exceptions["hostNamespaces"]:
            found.append(f"hostPort {','.join(map(str, host_ports))} on {name}")
        if (sc.get("seccompProfile") or {}).get("type") == "Unconfined":
            found.append(f"Unconfined seccomp on {name}")
        if sc.get("procMount", "Default") != "Default":
            found.append(f"procMount {sc['procMount']} on {name}")
    if namespace not in exceptions["hostPath"]:
        found += [f"hostPath volume {v.get('name')}" for v in spec.get("volumes") or [] if "hostPath" in v]
    if namespace not in exceptions["hostNamespaces"]:
        found += [field for field in ("hostNetwork", "hostPID", "hostIPC") if spec.get(field)]
    if ((spec.get("securityContext") or {}).get("seccompProfile") or {}).get("type") == "Unconfined":
        found.append("Unconfined pod seccomp")
    return found


def check_documents(docs, exceptions):
    errors = []
    for doc in docs:
        spec = pod_spec(doc)
        if spec is None:
            continue
        meta = doc.get("metadata", {})
        namespace = meta.get("namespace", "default")
        for v in violations(spec, namespace, exceptions):
            errors.append(f"{doc['kind']}/{namespace}/{meta.get('name')}: workload-baseline refuses {v}")
    return errors


def main():
    if sys.argv[1:] != ["--live"]:
        raise SystemExit("usage: pod_baseline.py --live  (offline checks run from check-policies.py)")
    pods = json.loads(subprocess.check_output(["kubectl", "get", "pods", "-A", "-o", "json"]))["items"]
    for pod in pods:
        pod.setdefault("kind", "Pod")
    errors = check_documents(pods, load_exceptions())
    print("\n".join(errors) if errors else f"PASS: {len(pods)} running pods pass workload-baseline")
    sys.exit(bool(errors))


if __name__ == "__main__":
    main()
