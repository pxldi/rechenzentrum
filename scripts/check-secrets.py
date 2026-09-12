#!/usr/bin/env python3
"""Check every Secret payload, including multi-document and nested List YAML.

Never prints secret values and never decrypts SOPS. Gitleaks separately scans
non-Secret files, configuration and documentation.
"""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def check_object(obj, location):
    errors = []
    if not isinstance(obj, dict):
        return errors
    if obj.get("kind") == "List":
        for item in obj.get("items", []):
            errors.extend(check_object(item, location))
    if obj.get("kind") == "Secret":
        for field in ("data", "stringData"):
            payload = obj.get(field) or {}
            if not isinstance(payload, dict):
                errors.append(f"{location}: invalid Secret {field}")
                continue
            for key, value in payload.items():
                # SOPS deliberately leaves empty strings unencrypted.
                if value == "":
                    continue
                if not (isinstance(value, str) and value.startswith("ENC[AES256_GCM,") and value.endswith("]")):
                    errors.append(f"{location}: unencrypted Secret {field}.{key}")
            if payload and not obj.get("sops", {}).get("mac", "").startswith("ENC["):
                errors.append(f"{location}: Secret payload lacks SOPS metadata")
    return errors


def main():
    errors = []
    count = 0
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(p in {".git", ".build", ".tools", ".venv"} for p in relative.parts):
            continue
        if path.is_file() and path.suffix in {".yaml", ".yml"}:
            count += 1
            try:
                for index, doc in enumerate(yaml.safe_load_all(path.read_text()), 1):
                    errors.extend(check_object(doc, f"{relative}:document {index}"))
            except yaml.YAMLError:
                errors.append(f"{relative}: invalid YAML (content suppressed)")
    print("\n".join(errors) if errors else f"PASS: checked {count} YAML files; all Secret payloads encrypted")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
