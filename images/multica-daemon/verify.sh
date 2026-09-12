#!/bin/sh
# Run inside the built image as uid 1000 with an empty environment, so what is
# proved is that the tool is reachable from a PATH nobody set up — the failure
# that cost two Codex review runs.
set -u

printf '%-14s %s\n' "id" "$(id)"
printf '%-14s %s\n' "PATH" "$PATH"
printf '%-14s %s\n' "os" "$(. /etc/os-release; echo "$PRETTY_NAME")"
echo

report() {
  name=$1
  shift
  if ! command -v "$name" >/dev/null 2>&1; then
    printf '%-14s %-12s %s\n' "$name" "MISSING" "not on PATH"
    return 1
  fi
  out=$("$@" 2>&1 | head -1 | tr -d '\r')
  printf '%-14s %-12s %s\n' "$name" "$(command -v "$name")" "$out"
}

echo "=== already present, now baked ==="
report go go version
report node node --version
report npm npm --version
report psql psql --version
report postgres postgres --version
report initdb initdb --version
report pg_ctl pg_ctl --version
report pg_dump pg_dump --version
report gh gh --version
report git git --version
report make make --version
report gcc gcc --version
report python3 python3 --version
report curl curl --version
report wget wget --version
report openssl openssl version
report rg rg --version

echo
echo "=== tier 1 ==="
report jq jq --version
report yq yq --version
report less less --version
report tree tree --version
report git-lfs git-lfs --version
report zstd zstd --version
report rsync rsync --version
report shellcheck shellcheck --version
report sqlite3 sqlite3 --version
report sqlc sqlc version
report goose goose --version
report ffmpeg ffmpeg -version
report fpcalc fpcalc -version

echo
echo "=== tier 2 ==="
report kubectl kubectl version --client=true
report helm helm version --short
report flux flux --version
report kustomize kustomize version
report stern stern --version
report k9s k9s version --short
report kubeconform kubeconform -v
report sops sops --version
report age age --version
report age-keygen age-keygen --version

echo
echo "=== tier 3 ==="
report crane crane version
report skopeo skopeo --version
report hadolint hadolint --version

echo
echo "=== playwright ==="
report playwright playwright --version
printf '%-14s %s\n' "browsers" "$PLAYWRIGHT_BROWSERS_PATH"
ls "$PLAYWRIGHT_BROWSERS_PATH" 2>/dev/null | sed 's/^/               /'
shell=$(find "$PLAYWRIGHT_BROWSERS_PATH" -name headless_shell -type f 2>/dev/null | head -1)
chrome=$(find "$PLAYWRIGHT_BROWSERS_PATH" -name chrome -type f 2>/dev/null | head -1)
[ -n "$chrome" ] && printf '%-14s %s\n' "chrome" "$("$chrome" --version 2>&1 | head -1)"
[ -n "$shell" ] && printf '%-14s %s\n' "headless_shell" "$("$shell" --version 2>&1 | head -1)"

echo
echo "=== android ==="
report java java -version
report javac javac -version
report sdkmanager sdkmanager --version
report adb adb --version
printf '%-14s %s\n' "JAVA_HOME" "${JAVA_HOME:-<unset>}"
printf '%-14s %s\n' "ANDROID_HOME" "${ANDROID_HOME:-<unset>}"
# The build proves these exist; this proves uid 1000 can still read them with a
# PATH and an environment it did not set, which is the failure this file is for.
for d in "${ANDROID_HOME:-/nonexistent}/platforms" "${ANDROID_HOME:-/nonexistent}/build-tools" "${ANDROID_HOME:-/nonexistent}/licenses"; do
  if [ -r "$d" ]; then
    printf '%-14s %s\n' "$(basename "$d")" "$(ls "$d" 2>/dev/null | tr '\n' ' ')"
  else
    printf '%-14s %s\n' "$(basename "$d")" "UNREADABLE — should not be"
  fi
done

echo
echo "=== explicitly absent ==="
for absent in docker terraform ansible aws gcloud az emulator; do
  if command -v "$absent" >/dev/null 2>&1; then
    printf '%-14s %s\n' "$absent" "PRESENT — should not be"
  else
    printf '%-14s %s\n' "$absent" "absent, as intended"
  fi
done
