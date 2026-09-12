#!/usr/bin/env python3
"""Validate rendered resources; fail on missing schemas, including CRDs.

SOPS metadata is transport-only. Replace encrypted Secret values with harmless
schema-compatible values in memory; never decrypt or persist plaintext.
"""
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
documents = [d for d in yaml.safe_load_all((ROOT / ".build/all.yaml").read_text()) if isinstance(d, dict)]
for doc in documents:
    if not isinstance(doc, dict):
        continue
    doc.pop("sops", None)
    if doc.get("kind") == "Secret":
        for field in ("data", "stringData"):
            if field in doc:
                doc[field] = {key: "" for key in doc[field]}
subprocess.run([
    "kubeconform", "-strict", "-summary", "-kubernetes-version", "1.33.0",
    "-schema-location", "default",
    "-schema-location", str(ROOT / "schemas/{{.Group}}-{{.ResourceKind}}-{{.ResourceAPIVersion}}.json"),
], input=yaml.safe_dump_all(documents), text=True, check=True, cwd=ROOT)
