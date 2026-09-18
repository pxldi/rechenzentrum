"""Init container for the ZeroClaw pod: wait until the MCP Services serve
this image's build.

ZeroClaw connects to its MCP servers once at startup and never retries.
When an image tag bump rolls the MCP Deployments and ZeroClaw in the same
reconcile, a plain /health check passes on the terminating old pod, and
ZeroClaw then registers the old tool list (or a stale session, HTTP 404)
and runs like that until someone restarts it. Both MCP Deployments and this
init container pin the same tag, so "the /health build equals my own
IMAGE_SHA" means the Service already points at the new pod.

Reachable but wrong build after the deadline still exits 0: a bot with the
old tools beats no bot, and the warning lands in the init container log.
"""

import json
import os
import sys
import time
import urllib.request

SERVERS = os.environ.get("MCP_URLS", "http://homelab-mcp:8000,http://tandoor-mcp:8000").split(",")
WANT = os.environ.get("IMAGE_SHA", "")
DEADLINE = float(os.environ.get("WAIT_SECONDS", "120"))


def build(url: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as r:  # noqa: S310
            return json.load(r).get("build")
    except Exception:  # noqa: BLE001
        return None


start = time.monotonic()
attempt = 0
seen: dict[str, str | None] = {}
while time.monotonic() - start < DEADLINE:
    attempt += 1
    seen = {u: build(u) for u in SERVERS}
    if all(b == WANT for b in seen.values()):
        print(f"MCP servers serve build {WANT[:12]} after {attempt} attempt(s)")
        sys.exit(0)
    time.sleep(3)

print(f"MCP servers not on build {WANT[:12]} after {attempt} attempts: {seen}; starting anyway", file=sys.stderr)
sys.exit(0)
