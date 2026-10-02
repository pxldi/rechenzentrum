"""The cluster as MCP tools: a read view, and three writes.

The reads are GETs against the API server through the pod's ServiceAccount,
whose ClusterRole grants get/list on workloads, pods, logs, events, routes,
Flux objects and Velero backups, and nothing on Secrets or ConfigMaps. The
writes are restart_workload, reconcile_flux and backup_now (see actions.py),
each asked for in the chat and held to its one effect by the
homelab-mcp-actions admission policy. There is deliberately no tool that
takes a raw kubectl command.
"""
