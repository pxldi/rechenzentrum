#!/usr/bin/env bash
# Create a private pull mirror on Forgejo for each named GitHub repository.
# Safe to re-run: a repository that already exists on Forgejo is skipped, so
# adding a name and running it again mirrors only the new one.
#
# Both tokens come from the environment so they never land in shell history or
# in this repository:
#   FORGEJO_TOKEN    Forgejo access token with write:repository and read:user
#   GH_MIRROR_TOKEN  GitHub fine-grained token, all repositories, Contents and
#                    Metadata read-only. Forgejo stores it to pull private repos.
#
# Usage: scripts/forgejo-mirror-github.sh [--copy] repo [repo ...]
#   --copy  one-time copy instead of a pull mirror, for repositories that no
#           longer change. Forgejo keeps no link to GitHub for these.
#   GITHUB_OWNER defaults to pxldi.
set -euo pipefail

FORGEJO_URL=${FORGEJO_URL:-https://git.pxldi.de}
OWNER=${GITHUB_OWNER:-pxldi}
MIRROR=true
if [[ ${1:-} == --copy ]]; then MIRROR=false; shift; fi
(( $# > 0 )) || { echo "usage: $0 repo [repo ...]" >&2; exit 2; }

: "${FORGEJO_TOKEN:?set FORGEJO_TOKEN}"
: "${GH_MIRROR_TOKEN:?set GH_MIRROR_TOKEN}"

api() {
  curl -sS -H "Authorization: token $FORGEJO_TOKEN" -H "Content-Type: application/json" "$@"
}

forgejo_user=$(api "$FORGEJO_URL/api/v1/user" | python3 -c 'import sys,json; print(json.load(sys.stdin)["login"])')
echo "$([[ $MIRROR == true ]] && echo Mirroring || echo Copying) github.com/$OWNER into $FORGEJO_URL/$forgejo_user"

for name in "$@"; do
  description=$(gh repo view "$OWNER/$name" --json description --jq '.description // ""')
  status=$(api -o /dev/null -w '%{http_code}' "$FORGEJO_URL/api/v1/repos/$forgejo_user/$name")
  if [[ $status == 200 ]]; then
    echo "exists $name"; continue
  fi
  body=$(NAME="$name" DESC="$description" OWNER="$OWNER" USER_="$forgejo_user" MIRROR="$MIRROR" python3 -c '
import json, os
print(json.dumps({
    "clone_addr": f"https://github.com/{os.environ["OWNER"]}/{os.environ["NAME"]}.git",
    "auth_token": os.environ["GH_MIRROR_TOKEN"],
    "repo_owner": os.environ["USER_"],
    "repo_name": os.environ["NAME"],
    "description": os.environ["DESC"],
    "mirror": os.environ["MIRROR"] == "true",
    "mirror_interval": "8h0m0s",
    "private": True,
    "lfs": True,
    "service": "git",
}))')
  code=$(api -o /tmp/forgejo-mirror-$$.json -w '%{http_code}' -X POST "$FORGEJO_URL/api/v1/repos/migrate" --data-binary @- <<<"$body")
  if [[ $code == 201 ]]; then
    echo "made  $name"
  else
    echo "FAIL  $name (HTTP $code): $(head -c 300 /tmp/forgejo-mirror-$$.json)"
  fi
done
rm -f /tmp/forgejo-mirror-$$.json
