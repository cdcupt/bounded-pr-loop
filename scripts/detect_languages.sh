#!/usr/bin/env bash
# detect_languages.sh
# Print a comma-separated list of overlay names that apply to this PR.
# An overlay applies if its sentinel file or extension appears either in
# the changed files OR in the repo root (so a Go repo always gets the go overlay,
# not just when go.mod itself was edited).
#
# Usage:
#   detect_languages.sh --files <path-to-changed-files-list> --repo <repo-root>
#
# Output (stdout): single line, e.g. "go,typescript"

set -euo pipefail

FILES=""
REPO="$(pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --files) FILES="$2"; shift 2 ;;
    --repo)  REPO="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$FILES" || ! -f "$FILES" ]]; then
  echo "Missing or unreadable --files" >&2
  exit 2
fi

declare -A FOUND

# Sentinel files at repo root → always-on overlays
[[ -f "$REPO/go.mod" ]]             && FOUND[go]=1
[[ -f "$REPO/Package.swift" ]]      && FOUND[swift]=1
[[ -f "$REPO/Cargo.toml" ]]         && FOUND[rust]=1
[[ -f "$REPO/pyproject.toml" || -f "$REPO/requirements.txt" || -f "$REPO/setup.py" ]] \
                                    && FOUND[python]=1
[[ -f "$REPO/tsconfig.json" ]]      && FOUND[typescript]=1
[[ -f "$REPO/package.json" && -z "${FOUND[typescript]:-}" ]] \
                                    && FOUND[javascript]=1
[[ -f "$REPO/Gemfile" ]]            && FOUND[ruby]=1
[[ -f "$REPO/pom.xml" || -f "$REPO/build.gradle" || -f "$REPO/build.gradle.kts" ]] \
                                    && FOUND[java]=1

# File extensions in the diff → additive overlays
while IFS= read -r f; do
  case "$f" in
    *.go)                FOUND[go]=1 ;;
    *.swift)             FOUND[swift]=1 ;;
    *.rs)                FOUND[rust]=1 ;;
    *.py)                FOUND[python]=1 ;;
    *.ts|*.tsx)          FOUND[typescript]=1 ;;
    *.js|*.jsx|*.mjs)    [[ -z "${FOUND[typescript]:-}" ]] && FOUND[javascript]=1 ;;
    *.rb)                FOUND[ruby]=1 ;;
    *.java|*.kt|*.kts)   FOUND[java]=1 ;;
    *.tf)                FOUND[terraform]=1 ;;
    *.sql)               FOUND[sql]=1 ;;
    Dockerfile|*Dockerfile|*.dockerfile) FOUND[docker]=1 ;;
  esac
done < "$FILES"

# Print sorted, comma-separated
keys="$(printf '%s\n' "${!FOUND[@]}" | sort | paste -sd, -)"
echo "$keys"
