"""A read-only view of the cluster as MCP tools.

Every tool is a GET against the API server through the pod's ServiceAccount,
whose ClusterRole grants get/list on workloads, pods, logs, events, routes,
Flux objects and Velero backups, and nothing on Secrets or ConfigMaps. There
is deliberately no tool that takes a raw kubectl command.
"""
