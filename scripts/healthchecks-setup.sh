#!/usr/bin/env bash
# One-time setup for the healthchecks.io dead-man's switches: the Watchdog
# route in kubernetes/infrastructure/monitoring/helmrelease.yaml, the backup and
# Renovate CronJobs, and nix/modules/autoupgrade.nix.
#
# Run from the repository root on the operator machine, the one with the SOPS
# age key. It asks for two keys from the healthchecks.io project's Settings
# page and never echoes either:
#
#   API key   "API Access" -> "Create API key" (the read-write one). Used here
#             only, to create the checks; it is not stored anywhere.
#   Ping key  "Ping key" -> "Create". Goes into the SOPS Secrets and onto the
#             node, and is what the jobs ping with.
#
# Steps, each safe to re-run:
#   1. create the checks below in the project (matched by name, so a re-run
#      does not duplicate them)
#   2. write the ping key into the five healthchecks-secret.yaml files with
#      `sops set`; commit and push those afterwards
#   3. install the ping key on the node for nixos-upgrade, over ssh
#      (HC_SSH_HOST, default "rechenzentrum"; HC_SSH_HOST=- skips it)
set -euo pipefail

api=https://healthchecks.io/api/v3/checks/
ssh_host=${HC_SSH_HOST:-rechenzentrum}

if [ -z "${HC_API_KEY:-}" ]; then
  read -rsp "healthchecks.io API key (read-write): " HC_API_KEY; echo
fi
if [ -z "${HC_PING_KEY:-}" ]; then
  read -rsp "healthchecks.io ping key: " HC_PING_KEY; echo
fi
[ -n "$HC_API_KEY" ] && [ -n "$HC_PING_KEY" ] || { echo "both keys are required" >&2; exit 1; }

# name|schedule-or-period|grace seconds|description
#
# Cron schedules are the CronJobs' and the timer's own, in their time zone.
# Grace is how long after the due time a check may stay quiet, and doubles as
# the longest a started run may take before it counts as hung.
checks=(
  "watchdog|300|600|Alertmanager Watchdog, every 2m. Missing = node, WAN, k3s, Prometheus or Alertmanager down."
  "renovate|30 3 * * *|7200|Renovate CronJob (renovate namespace)."
  "karakeep-db-backup|30 3 * * *|3600|SQLite copy for Velero (karakeep namespace)."
  "wealthfolio-db-backup|45 3 * * *|3600|SQLite copy for Velero (wealthfolio namespace)."
  "snacky-db-backup|0 4 * * *|3600|SQLite copy for Velero (snacky namespace)."
  "nixos-upgrade|45 4 * * *|7200|NixOS system.autoUpgrade on the node."
)

echo "== checks"
for entry in "${checks[@]}"; do
  IFS='|' read -r name when grace desc <<<"$entry"
  if [[ $when =~ ^[0-9]+$ ]]; then
    timing=$(printf '"timeout": %s' "$when")
  else
    timing=$(printf '"schedule": "%s", "tz": "Europe/Berlin"' "$when")
  fi
  body=$(printf '{"name": "%s", "slug": "%s", "tags": "rechenzentrum", "desc": "%s", %s, "grace": %s, "channels": "*", "unique": ["name"]}' \
    "$name" "$name" "$desc" "$timing" "$grace")
  code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$api" \
    -H "X-Api-Key: $HC_API_KEY" -H 'Content-Type: application/json' --data "$body")
  case $code in
    201) echo "created  $name" ;;
    200) echo "exists   $name" ;;
    *) echo "failed   $name (HTTP $code)" >&2; exit 1 ;;
  esac
done

echo "== secrets"
command -v sops >/dev/null || { echo "sops not found" >&2; exit 1; }
for f in \
  kubernetes/infrastructure/renovate/healthchecks-secret.yaml \
  kubernetes/apps/karakeep/healthchecks-secret.yaml \
  kubernetes/apps/wealthfolio/healthchecks-secret.yaml \
  kubernetes/apps/snacky/healthchecks-secret.yaml; do
  printf '"%s"' "$HC_PING_KEY" | sops set --value-stdin "$f" '["stringData"]["ping-key"]'
  echo "set      $f"
done
f=kubernetes/infrastructure/monitoring/healthchecks-secret.yaml
printf '"https://hc-ping.com/%s/watchdog"' "$HC_PING_KEY" |
  sops set --value-stdin "$f" '["stringData"]["watchdog-url"]'
echo "set      $f"

echo "== node"
if [ "$ssh_host" = "-" ]; then
  echo "skipped; on the node run: sudo install -D -m 600 /dev/stdin /var/lib/healthchecks/ping-key"
else
  printf '%s' "$HC_PING_KEY" |
    ssh "$ssh_host" 'sudo install -D -m 600 /dev/stdin /var/lib/healthchecks/ping-key'
  echo "wrote    $ssh_host:/var/lib/healthchecks/ping-key"
fi

echo
echo "Done. Commit and push the five healthchecks-secret.yaml files."
