#!/usr/bin/env bash
# Mirror the Backblaze B2 backup buckets onto a local disk, such as an external
# drive plugged in now and then. It copies the objects exactly as they are:
# Velero's kopia repository (encrypted with the kopia repository password), the
# CNPG base backups and WAL (gzip only, NOT encrypted) and the Terraform state.
# Encrypt the drive itself.
#
# Usage:
#   scripts/b2-offline-copy.sh --init <dir>   first run: mark <dir> as the copy
#   scripts/b2-offline-copy.sh <dir> [rclone flags...]
#
# Extra flags go to every `rclone sync`, for example --dry-run or --bwlimit 20M.
#
# Needs an rclone remote (B2_REMOTE, default "b2-offline") holding a B2
# application key with read-only access. The script only ever reads from B2;
# a read-only key makes that a guarantee rather than a promise.
#
# Safe to re-run:
#   - <dir> must carry the marker file written by --init, so an unmounted drive
#     (an empty mount point on the system disk) is refused instead of filled.
#   - Files that disappeared from or changed in B2 since the last run are moved
#     to <dir>/.replaced/<timestamp>/ rather than deleted, and pruned after
#     KEEP_REPLACED_DAYS (default 90). A bucket that got emptied therefore does
#     not empty the copy.
#   - Only the current version of each object is copied; Object Lock's hidden
#     versions stay in B2.
#
# Avoid the backup window (roughly 00:00-04:00 Europe/Berlin): a sync that
# overlaps a running backup may catch it half-written. The next run fixes it.
set -euo pipefail

remote=${B2_REMOTE:-b2-offline}
buckets=${B2_BUCKETS:-rechenzentrum-backups rechenzentrum-cnpg rechenzentrum-tf-state}
keep_days=${KEEP_REPLACED_DAYS:-90}
marker=.b2-offline-copy

usage() { sed -n '9,10p' "$0" | sed 's/^# *//' >&2; exit 2; }

init=false
if [ "${1:-}" = "--init" ]; then init=true; shift; fi
[ $# -ge 1 ] || usage
dest=${1%/}
shift

command -v rclone >/dev/null || { echo "rclone is not installed" >&2; exit 1; }
rclone listremotes | grep -qx "$remote:" || {
  echo "no rclone remote named '$remote' (set B2_REMOTE or run 'rclone config')" >&2
  exit 1
}

if $init; then
  [ -d "$dest" ] || { echo "$dest does not exist" >&2; exit 1; }
  if [ "$(findmnt -no TARGET -T "$dest" 2>/dev/null || echo /)" = / ]; then
    echo "$dest is on the root filesystem, not on a separate drive" >&2
    exit 1
  fi
  date -u +%FT%TZ >"$dest/$marker"
  echo "marked $dest as the B2 offline copy"
elif [ ! -f "$dest/$marker" ]; then
  echo "$dest/$marker is missing: drive not mounted, or not set up with --init" >&2
  exit 1
fi

hour=$(TZ=Europe/Berlin date +%H)
if [ "$hour" -lt 4 ]; then
  echo "warning: inside the nightly backup window, the newest backup may be incomplete" >&2
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
status=0
for bucket in $buckets; do
  echo "== $bucket"
  if ! rclone sync "$remote:$bucket" "$dest/$bucket" \
      --backup-dir "$dest/.replaced/$stamp/$bucket" \
      --fast-list --transfers 8 --checkers 16 \
      --stats 1m --stats-one-line -v "$@"; then
    echo "sync of $bucket failed" >&2
    status=1
  fi
done

case " $* " in *" --dry-run "*|*" -n "*) exit $status ;; esac

if [ -d "$dest/.replaced" ]; then
  find "$dest/.replaced" -mindepth 1 -maxdepth 1 -type d -mtime +"$keep_days" \
    -exec rm -rf {} +
fi

{
  echo "finished: $(date -u +%FT%TZ)"
  echo "result: $([ $status -eq 0 ] && echo ok || echo FAILED)"
  for dir in $buckets .replaced; do
    if [ -d "$dest/$dir" ]; then du -sh "$dest/$dir"; fi
  done
} | tee "$dest/LAST_SYNC"
exit $status
