#!/usr/bin/env python3
"""Check kubernetes/apps/planka/theme.css against the running Planka build.

Planka names its CSS module classes _<local>_<hash>_<line>, and the hash
changes whenever Planka edits that module. After an upgrade, run:

    kubectl exec -n planka deploy/planka -- sh -c 'cat /app/public/assets/index-*.css' > /tmp/planka.css
    python3 scripts/planka-css-hashes.py /tmp/planka.css

For every hash theme.css uses, it prints OK, or the hashes in the new build
whose module has every class name theme.css uses with the old one.
"""
import collections
import re
import sys
from pathlib import Path

THEME = Path(__file__).resolve().parents[1] / 'kubernetes/apps/planka/theme.css'

built = Path(sys.argv[1]).read_text()
built_locals = collections.defaultdict(set)
for local, h in re.findall(r'\._([A-Za-z][A-Za-z0-9]*)_([a-z0-9]{5})_\d+', built):
    built_locals[h].add(local)

used = collections.defaultdict(set)
for local, h in re.findall(r'_([A-Za-z][A-Za-z0-9]*)_([a-z0-9]{5})_', THEME.read_text()):
    used[h].add(local)

stale = 0
for h, locals_ in sorted(used.items()):
    if locals_ <= built_locals.get(h, set()):
        print(f'OK     {h}  {", ".join(sorted(locals_))}')
        continue
    stale += 1
    candidates = [c for c, ls in built_locals.items() if locals_ <= ls]
    print(f'STALE  {h}  {", ".join(sorted(locals_))}  ->  {", ".join(candidates) or "no match"}')

sys.exit(1 if stale else 0)
