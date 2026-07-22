#!/usr/bin/env bash
# Relative markdown links rot silently as files move. Absolute URLs are a
# reviewer's job; this checks only what the repo can verify itself.
#
# A trailing :NNN is the file:line convention used throughout these docs, not
# part of the path — strip it before resolving.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

rc=0
while IFS= read -r md; do
  while IFS= read -r target; do
    path="${target%%#*}"      # drop #anchor
    path="${path%:[0-9]*}"    # drop :line
    [ -z "$path" ] && continue
    if [ ! -e "$(dirname "$md")/$path" ]; then
      echo "::error file=$md::broken relative link -> $target"
      rc=1
    fi
  done < <(grep -oE '\]\(([^)]+)\)' "$md" \
           | sed -E 's/^\]\(//; s/\)$//' \
           | grep -vE '^(https?:|mailto:|#)' || true)
done < <(git ls-files '*.md')

[ "$rc" -eq 0 ] && echo "All relative markdown links resolve."
exit "$rc"
