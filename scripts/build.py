#!/usr/bin/env python3
"""Build all Flux reconciliation roots, including their patches, offline."""
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".build"


def main():
    OUT.mkdir(exist_ok=True)
    queue = [(ROOT / "kubernetes/flux-system/gotk-sync.yaml", "flux-system")]
    seen = set()
    identities = {}
    while queue:
        source, name = queue.pop(0)
        for ks in yaml.safe_load_all(source.read_text()):
            if not isinstance(ks, dict) or ks.get("kind") != "Kustomization" or ks.get("metadata", {}).get("name") != name:
                continue
            if (ks["metadata"].get("namespace", "flux-system"), name) in seen:
                continue
            seen.add((ks["metadata"].get("namespace", "flux-system"), name))
            path = (ROOT / ks["spec"]["path"]).resolve()
            if not path.is_relative_to(ROOT):
                raise SystemExit("Flux path escapes repository")
            rendered = subprocess.check_output([
                "flux", "build", "kustomization", name,
                "--path", str(path), "--kustomization-file", str(source),
                "--dry-run", "--namespace", ks["metadata"].get("namespace", "flux-system"),
            ], cwd=ROOT, text=True)
            target = OUT / f"{name}.yaml"
            target.write_text(rendered)
            docs = [d for d in yaml.safe_load_all(rendered) if isinstance(d, dict)]
            for doc in docs:
                meta = doc.get("metadata", {})
                identity = (doc["apiVersion"].split("/")[0] if "/" in doc["apiVersion"] else "", doc["kind"], meta.get("namespace", ""), meta.get("name", ""))
                if identity in identities:
                    raise SystemExit(f"Duplicate ownership: {identity} in {name} and {identities[identity]}")
                identities[identity] = name
                if doc.get("apiVersion", "").startswith("kustomize.toolkit.fluxcd.io/") and doc.get("kind") == "Kustomization":
                    queue.append((target, meta["name"]))
            print(f"PASS: {name}: {len(docs)} resources")
    (OUT / "all.yaml").write_text("\n---\n".join((OUT / f"{name}.yaml").read_text() for _, name in sorted(seen)))
    print(f"PASS: {len(identities)} unique resources across {len(seen)} Flux roots")


if __name__ == "__main__":
    main()
