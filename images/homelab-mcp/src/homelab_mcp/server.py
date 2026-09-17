import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from kubernetes import client, config
from mcp.server import MCPServer
from pydantic import Field

from serve import guarded

mcp = MCPServer("homelab")

MAX_LOG_CHARS = 8000


@lru_cache(maxsize=1)
def _load() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # Running outside the cluster, e.g. a local smoke test.
        config.load_kube_config()


def _core() -> client.CoreV1Api:
    _load()
    return client.CoreV1Api()


def _apps() -> client.AppsV1Api:
    _load()
    return client.AppsV1Api()


def _custom() -> client.CustomObjectsApi:
    _load()
    return client.CustomObjectsApi()


def _age(ts: datetime | None) -> str:
    if ts is None:
        return ""
    delta = datetime.now(timezone.utc) - ts
    s = int(delta.total_seconds())
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _condition(obj: dict, kind: str = "Ready") -> tuple[str, str]:
    for c in (obj.get("status") or {}).get("conditions") or []:
        if c.get("type") == kind:
            return c.get("status", "Unknown"), (c.get("message") or "")[:300]
    return "Unknown", ""


# --- tools -----------------------------------------------------------------


@mcp.tool()
@guarded(client.ApiException, RuntimeError)
def list_services() -> list[dict]:
    """Every HTTP route the cluster serves: hostname, namespace and whether it is gated to the LAN and tailnet."""
    routes = _custom().list_cluster_custom_object("traefik.io", "v1alpha1", "ingressroutes")
    out = []
    for r in routes.get("items", []):
        for rule in (r.get("spec") or {}).get("routes") or []:
            match = rule.get("match", "")
            hosts = re.findall(r"Host\(`([^`]+)`\)", match)
            if not hosts:
                continue
            mws = [m.get("name") for m in rule.get("middlewares") or []]
            if "PathPrefix(`/outpost.goauthentik.io/`)" in match:
                continue
            out.append(
                {
                    "host": hosts[0],
                    "namespace": r["metadata"]["namespace"],
                    "route": r["metadata"]["name"],
                    "lan_only": "internal-only" in mws,
                    "authentik": "authentik-forward-auth" in mws,
                    "path_rule": match if "Path" in match else "",
                }
            )
    return sorted(out, key=lambda x: x["host"])


@mcp.tool()
@guarded(client.ApiException, RuntimeError)
def list_workloads(namespace: str = Field("", description="Empty for all namespaces.")) -> list[dict]:
    """Deployments, StatefulSets and DaemonSets with ready/desired counts and images."""
    apps = _apps()
    ns = namespace or None
    out = []
    for kind, lister in (
        ("Deployment", apps.list_deployment_for_all_namespaces if not ns else lambda: apps.list_namespaced_deployment(ns)),
        ("StatefulSet", apps.list_stateful_set_for_all_namespaces if not ns else lambda: apps.list_namespaced_stateful_set(ns)),
        ("DaemonSet", apps.list_daemon_set_for_all_namespaces if not ns else lambda: apps.list_namespaced_daemon_set(ns)),
    ):
        for w in lister().items:
            st = w.status
            if kind == "DaemonSet":
                desired, ready = st.desired_number_scheduled or 0, st.number_ready or 0
            else:
                desired, ready = w.spec.replicas or 0, st.ready_replicas or 0
            out.append(
                {
                    "kind": kind,
                    "namespace": w.metadata.namespace,
                    "name": w.metadata.name,
                    "ready": f"{ready}/{desired}",
                    "healthy": ready == desired,
                    "images": [c.image for c in w.spec.template.spec.containers],
                }
            )
    return sorted(out, key=lambda x: (x["namespace"], x["name"]))


@mcp.tool()
@guarded(client.ApiException, RuntimeError)
def workload_status(namespace: str, name: str) -> dict:
    """One workload in detail: rollout conditions, its pods with restarts and phase, and its recent events."""
    apps, core = _apps(), _core()
    obj: Any = None
    kind = ""
    for k, getter in (("Deployment", apps.read_namespaced_deployment), ("StatefulSet", apps.read_namespaced_stateful_set), ("DaemonSet", apps.read_namespaced_daemon_set)):
        try:
            obj = getter(name, namespace)
            kind = k
            break
        except client.ApiException as e:
            if e.status != 404:
                raise
    if obj is None:
        raise RuntimeError(f"no Deployment, StatefulSet or DaemonSet {namespace}/{name}")
    selector = ",".join(f"{k}={v}" for k, v in (obj.spec.selector.match_labels or {}).items())
    pods = core.list_namespaced_pod(namespace, label_selector=selector).items
    pod_rows = []
    for p in pods:
        cs = p.status.container_statuses or []
        pod_rows.append(
            {
                "name": p.metadata.name,
                "phase": p.status.phase,
                "ready": f"{sum(1 for c in cs if c.ready)}/{len(cs)}",
                "restarts": sum(c.restart_count for c in cs),
                "age": _age(p.metadata.creation_timestamp),
                "waiting": [
                    f"{c.name}: {c.state.waiting.reason}" for c in cs if c.state and c.state.waiting and c.state.waiting.reason
                ],
            }
        )
    conditions = [
        {"type": c.type, "status": c.status, "reason": c.reason, "message": (c.message or "")[:200]}
        for c in (obj.status.conditions or [])
    ]
    names = {name, *[p["name"] for p in pod_rows]}
    evs = core.list_namespaced_event(namespace).items
    events = [
        {"age": _age(e.last_timestamp or e.event_time), "type": e.type, "reason": e.reason, "object": e.involved_object.name, "message": (e.message or "")[:200]}
        for e in evs
        if e.involved_object.name in names
    ]
    events.sort(key=lambda x: x["age"])
    return {"kind": kind, "namespace": namespace, "name": name, "conditions": conditions, "pods": pod_rows, "events": events[-15:]}


@mcp.tool()
@guarded(client.ApiException, RuntimeError)
def pod_logs(
    namespace: str,
    pod: str,
    container: str = Field("", description="Needed only for multi-container pods."),
    tail_lines: int = Field(100, ge=1, le=1000),
    previous: bool = Field(False, description="Logs of the previous, crashed container instead of the running one."),
) -> str:
    """The last lines of a pod's log, capped at 8000 characters."""
    text = _core().read_namespaced_pod_log(
        pod, namespace, container=container or None, tail_lines=tail_lines, previous=previous, timestamps=True
    )
    if len(text) > MAX_LOG_CHARS:
        return "...[truncated]...\n" + text[-MAX_LOG_CHARS:]
    return text


@mcp.tool()
@guarded(client.ApiException, RuntimeError)
def events(
    namespace: str = Field("", description="Empty for all namespaces."),
    warnings_only: bool = True,
    limit: int = Field(50, ge=1, le=200),
) -> list[dict]:
    """Recent Kubernetes events, newest last. Warnings only by default."""
    core = _core()
    evs = (core.list_namespaced_event(namespace) if namespace else core.list_event_for_all_namespaces()).items
    rows = []
    for e in evs:
        if warnings_only and e.type != "Warning":
            continue
        ts = e.last_timestamp or e.event_time or e.metadata.creation_timestamp
        rows.append(
            {
                "time": ts.isoformat() if ts else "",
                "namespace": e.metadata.namespace,
                "type": e.type,
                "reason": e.reason,
                "object": f"{e.involved_object.kind}/{e.involved_object.name}",
                "count": e.count,
                "message": (e.message or "")[:200],
            }
        )
    rows.sort(key=lambda x: x["time"])
    return rows[-limit:]


@mcp.tool()
@guarded(client.ApiException, RuntimeError)
def flux_status() -> dict:
    """Flux Kustomizations and HelmReleases: ready, applied revision, and the message of anything not ready."""
    cu = _custom()
    ks = cu.list_cluster_custom_object("kustomize.toolkit.fluxcd.io", "v1", "kustomizations").get("items", [])
    hr = cu.list_cluster_custom_object("helm.toolkit.fluxcd.io", "v2", "helmreleases").get("items", [])

    def row(o: dict, rev_key: str) -> dict:
        status, msg = _condition(o)
        return {
            "namespace": o["metadata"]["namespace"],
            "name": o["metadata"]["name"],
            "ready": status,
            "revision": (o.get("status") or {}).get(rev_key, ""),
            "message": msg if status != "True" else "",
        }

    kust = [row(o, "lastAppliedRevision") for o in ks]
    rel = [row(o, "lastAppliedRevision") for o in hr]
    return {
        "kustomizations": kust,
        "helmreleases": rel,
        "not_ready": [f"{r['namespace']}/{r['name']}" for r in kust + rel if r["ready"] != "True"],
    }


@mcp.tool()
@guarded(client.ApiException, RuntimeError)
def backups(limit: int = Field(20, ge=1, le=100)) -> dict:
    """Velero: the newest backups with phase and errors, and each schedule's last run."""
    cu = _custom()
    bks = cu.list_namespaced_custom_object("velero.io", "v1", "velero", "backups").get("items", [])
    scheds = cu.list_namespaced_custom_object("velero.io", "v1", "velero", "schedules").get("items", [])
    rows = []
    for b in bks:
        st = b.get("status") or {}
        rows.append(
            {
                "name": b["metadata"]["name"],
                "schedule": (b["metadata"].get("labels") or {}).get("velero.io/schedule-name", ""),
                "phase": st.get("phase", ""),
                "started": st.get("startTimestamp", ""),
                "expires": st.get("expiration", ""),
                "errors": st.get("errors", 0),
                "warnings": st.get("warnings", 0),
            }
        )
    rows.sort(key=lambda x: x["started"])
    schedules = [
        {
            "name": s["metadata"]["name"],
            "cron": (s.get("spec") or {}).get("schedule", ""),
            "paused": bool((s.get("spec") or {}).get("paused")),
            "last_backup": (s.get("status") or {}).get("lastBackup", ""),
            "phase": (s.get("status") or {}).get("phase", ""),
        }
        for s in scheds
    ]
    return {"backups": rows[-limit:], "schedules": schedules}
