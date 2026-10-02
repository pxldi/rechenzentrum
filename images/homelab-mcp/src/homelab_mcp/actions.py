"""The decisions behind the homelab server's three write tools, without the
Kubernetes client, so they can be tested on their own.

The tools are deliberately small: restart a workload, ask Flux to reconcile,
start a backup from an existing schedule. Each one can only do what its
Kubernetes permission allows, and the homelab-mcp-actions admission policy
checks the request again on the API server, so a bug here cannot turn a
"reconcile" into a spec change. This module is the first of those layers,
the one that gives the model a readable refusal.
"""

from datetime import datetime

# Restarting a pod here takes something down that the rest depends on, or
# the bot itself. The admission policy refuses the same list.
PROTECTED_NAMESPACES = frozenset({"kube-system", "kube-public", "kube-node-lease", "flux-system", "cnpg-system", "chatops"})

REQUESTED_AT = "reconcile.fluxcd.io/requestedAt"
FLUX_KINDS = {
    "kustomization": ("kustomize.toolkit.fluxcd.io", "v1", "kustomizations"),
    "helmrelease": ("helm.toolkit.fluxcd.io", "v2", "helmreleases"),
}
MANUAL_LABEL = "rechenzentrum.dev/triggered-by"


def check_restartable(namespace: str, pod_labels: list[dict]) -> None:
    """Raise RuntimeError with the reason when the bot must not restart these pods."""
    if namespace in PROTECTED_NAMESPACES:
        raise RuntimeError(f"{namespace} is protected; restart it from a terminal if it really needs it")
    if any("cnpg.io/cluster" in (labels or {}) for labels in pod_labels):
        raise RuntimeError("that is a CNPG database instance; the operator restarts those, not the bot")
    if not pod_labels:
        raise RuntimeError("the workload has no pods to restart")


def flux_kind(kind: str) -> tuple[str, str, str]:
    try:
        return FLUX_KINDS[kind.lower()]
    except KeyError:
        raise RuntimeError(f"kind must be one of {', '.join(sorted(FLUX_KINDS))}") from None


def reconcile_patch(now: datetime) -> dict:
    """The only change reconcile_flux makes: the annotation `flux reconcile` sets."""
    return {"metadata": {"annotations": {REQUESTED_AT: now.isoformat()}}}


def manual_backup(schedule: dict, now: datetime) -> dict:
    """A Backup that is the schedule's template, run now.

    Copied verbatim, so the backup covers what the nightly one covers and
    expires like it. No schedule-name label: Velero would count it as one of
    the schedule's own runs and age it out with them.
    """
    template = (schedule.get("spec") or {}).get("template")
    if not template:
        raise RuntimeError(f"schedule {schedule['metadata']['name']} has no template")
    if template.get("hooks"):
        # The admission policy refuses hooks from the bot: a hook runs a
        # command inside the pods it backs up.
        raise RuntimeError("that schedule runs backup hooks, which the bot may not trigger")
    name = schedule["metadata"]["name"]
    return {
        "apiVersion": "velero.io/v1",
        "kind": "Backup",
        "metadata": {
            "name": f"{name}-manual-{now.strftime('%Y%m%d%H%M%S')}",
            "namespace": "velero",
            "labels": {MANUAL_LABEL: "homelab-mcp", "rechenzentrum.dev/from-schedule": name},
        },
        "spec": template,
    }
