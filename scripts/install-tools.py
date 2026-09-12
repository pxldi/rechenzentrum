#!/usr/bin/env python3
"""Install pinned Linux amd64 validators with SHA256 verification."""
from pathlib import Path
import hashlib
import io
import json
import platform
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if platform.system() != 'Linux' or platform.machine() not in {'x86_64', 'amd64'}:
    raise SystemExit('This tool lock targets Linux amd64; install matching versions manually on other platforms')
out = ROOT / '.tools'
out.mkdir(exist_ok=True)
for name, source in json.loads((ROOT / 'scripts/tools.lock.json').read_text()).items():
    request = urllib.request.Request(source['url'], headers={'User-Agent': 'rechenzentrum-ci'})
    with urllib.request.urlopen(request, timeout=60) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != source['sha256']:
        raise SystemExit(f'Checksum mismatch: {name}')
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        member = tar.getmember(name)
        if not member.isfile():
            raise SystemExit(f'Unexpected archive member: {name}')
        (out / name).write_bytes(tar.extractfile(member).read())
    (out / name).chmod(0o755)
    print(f'Installed {name}, checksum verified')
