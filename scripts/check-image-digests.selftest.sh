#!/usr/bin/env bash
# Proves check-image-digests.sh can fail.
#
# Every shape the old denylist let through must be red here — a floating
# major, a release-looking tag, a truncated digest — and the two committed
# compose files, plus a digest-only reference, must be green. Then one
# digest is stripped from a copy of compose.override.yaml and the gate has
# to name that line. Same premise as preflight-selftest.sh: a gate that
# cannot fail reads as coverage and protects nothing.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

GATE=scripts/check-image-digests.sh
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

rc=0
ok()  { printf '  \033[32mok\033[0m   %s\n' "$1"; }
err() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }

# expect <pass|fail> <label> [FILE...]: refs on stdin when no file is given.
expect() {
  local want="$1" label="$2"; shift 2
  local out status
  out="$($GATE "$@" 2>&1)"; status=$?
  case "$want:$status" in
    pass:0|fail:1) ok "$label" ;;
    *) err "$label (exit $status, wanted $want)"; printf '%s\n' "$out" | sed 's/^/        /' ;;
  esac
}

D="$(printf '%064d' 0 | tr 0 a)"   # sixty-four hex digits

echo "committed files: pinned"
expect pass "deploy/compose.override.yaml passes as committed" deploy/compose.override.yaml </dev/null
expect pass "the greffon compose passes as committed" deploy/greffon/visio/1.0/docker-compose.yml </dev/null

echo "rendered shapes: each must be judged on the digest alone"
printf 'postgres:16@sha256:%s\n' "$D" | expect pass "tag plus digest"
printf 'lasuite/meet-backend@sha256:%s\n' "$D" | expect pass "digest without a tag (immutable, if less readable)"
printf 'postgres:16\n' | expect fail "floating major (passed the old denylist)"
printf 'lasuite/meet-backend:v1.24.0\n' | expect fail "release-looking tag (passed the old denylist)"
printf 'lasuite/meet-backend:latest\n' | expect fail "latest"
printf 'lasuite/meet-backend\n' | expect fail "untagged (implicitly latest)"
printf 'postgres:16@sha256:%s\n' "${D%?}" | expect fail "digest one hex digit short"
printf 'postgres:16@sha256:%sZ\n' "${D%?}" | expect fail "digest with a non-hex character"
printf 'postgres:16@sha256:%s\nredis:7.4-alpine\n' "$D" | expect fail "one pinned, one not — the list fails as a whole"
printf '' | expect fail "empty list (an empty list is not a pinned list)"

echo "static shapes: the file parser"
# `image:` lines only: the file's own comments spell out the `tag@sha256:`
# form, and a mutation that edits a comment proves nothing.
awk '{ if (!done && /^[[:space:]]*image:/ && sub(/@sha256:[0-9a-f]+/, "")) done = 1; print }' \
  deploy/compose.override.yaml > "$WORK/override.yaml"
if diff -q deploy/compose.override.yaml "$WORK/override.yaml" >/dev/null; then
  err "the mutation did not strip a digest — nothing below proves anything"
fi
out="$($GATE "$WORK/override.yaml" 2>&1)"; status=$?
stripped="$(diff deploy/compose.override.yaml "$WORK/override.yaml" | sed -n 's/^> *image: *//p' | head -1)"
if [ "$status" -eq 1 ] && printf '%s\n' "$out" | grep -q "^FAIL .*: ${stripped}"; then
  ok "one digest stripped from a copy of compose.override.yaml: red, and the line is named ($stripped)"
else
  err "one digest stripped from compose.override.yaml was not named (exit $status)"
  printf '%s\n' "$out" | sed 's/^/        /'
fi
printf 'services:\n  a:\n    # image: nginx:latest\n    image: "nginx:1.25@sha256:%s"\n' "$D" > "$WORK/quoted.yaml"
expect pass "quoted reference passes; a commented-out floating one is not a reference" "$WORK/quoted.yaml" </dev/null
printf 'services:\n  a:\n    build: .\n' > "$WORK/noimage.yaml"
expect fail "a compose file with no image: line at all" "$WORK/noimage.yaml" </dev/null
expect fail "a missing file" "$WORK/does-not-exist.yaml" </dev/null

echo
if [ "$rc" -eq 0 ]; then echo "check-image-digests self-test passed: the gate can still fail."
else echo "check-image-digests self-test FAILED: the gate no longer detects a floating reference."; fi
exit "$rc"
