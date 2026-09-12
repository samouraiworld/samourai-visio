#!/usr/bin/env bash
# Every image reference carries its content digest, or this gate is red.
#
# A tag is a pointer its registry owner can move: `postgres:16` is a
# different image after every upstream rebuild, and a tag that LOOKS
# immutable (`v1.24.0`) is a convention, not a guarantee. The CI step this
# replaces rejected a denylist — `latest`, `main`, `master`, `edge`, untagged
# — and passed everything else, which read as pinning while pinning nothing.
# This is the allowlist: a reference is pinned only if it ends in `@sha256:`
# followed by sixty-four hex digits. The tag stays in front of the digest so
# `docker compose config --images`, the RUNBOOK's image records and a reader
# still see which release it is.
#
# Usage:
#   scripts/check-image-digests.sh FILE...     # static: every `image:` in each compose file
#   docker compose config --images | scripts/check-image-digests.sh
#                                              # rendered: what compose will actually pull
#
# Prints PASS or FAIL per reference and exits 1 on any FAIL — or on no
# reference at all, because an empty list is not a pinned list. Asserts on
# output, never on grep exit codes (repo rule). Proven by
# check-image-digests.selftest.sh.

set -uo pipefail

refs=""
if [ $# -gt 0 ]; then
  for f in "$@"; do
    [ -f "$f" ] || { echo "FAIL $f: no such file"; exit 1; }
    # `image: value`, optionally quoted; a commented-out line does not start
    # with `image:` after its indentation, so it is not a reference.
    while IFS= read -r ref; do
      refs="${refs}${f}: ${ref}"$'\n'
    done < <(sed -nE 's/^[[:space:]]*image:[[:space:]]*"?([^"[:space:]#]+)"?.*$/\1/p' "$f")
  done
else
  while IFS= read -r ref; do
    [ -n "$ref" ] && refs="${refs}stdin: ${ref}"$'\n'
  done
fi

if [ -z "$refs" ]; then
  echo "FAIL no image reference found — an empty list is not a pinned list"
  exit 1
fi

status=0
count=0
while IFS= read -r entry; do
  [ -n "$entry" ] || continue
  count=$((count + 1))
  ref="${entry#*: }"
  if printf '%s\n' "$ref" | grep -qE '@sha256:[0-9a-f]{64}$'; then
    echo "PASS $entry"
  else
    echo "FAIL $entry — no content digest (tag@sha256:<64 hex> required; a tag alone can be moved)"
    status=1
  fi
done <<< "$refs"

if [ "$status" -eq 0 ]; then
  echo "All $count image references are pinned by digest."
else
  echo "Image references without a digest: resolve one with scripts/resolve-image-digest.sh IMAGE:TAG"
fi
exit "$status"
