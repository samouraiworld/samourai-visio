#!/usr/bin/env bash
# Self-test for check-gateway-brake.sh: each of its verdicts can still fail,
# and fails naming its own cause.
#
# Runs the check against the repository's template, which must pass, then
# against copies broken one way each. Every broken copy must make the check
# exit 1 AND print the FAIL line of the case that owns that defect: the exit
# status is all CI consumes, and the message is what tells a reader which
# case still works — a check that fails for the wrong reason has only
# happened to fail.
#
# Each mutation must change exactly one template line, so a sed that stops
# matching (a renamed directive, a realigned column) is reported here as a
# broken fixture rather than passing as an unchanged template.
#
# Slow by nature: every case is a full run of the check (about half a minute).

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

TEMPLATE=deploy/nginx/default.conf.template
WORK="$(mktemp -d)"
FINISHED=0
# Anything that ends this script before its verdict must not exit 0.
trap 'rm -rf "$WORK"; [ "$FINISHED" = 1 ] || { echo "gateway brake self-test ABORTED before its verdict — nothing was proven"; exit 1; }' EXIT

rc=0
n=0
ok()  { printf '  \033[32mok\033[0m   %s\n' "$1"; }
err() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }

echo "Gateway brake self-test — the check against broken copies of the template"
echo

# run_case <label> <sed expression, or empty> <expected exit> <FAIL line pattern, or empty>
# The pattern is an extended regex, so a text every case prints (a verdict
# phrase) can be anchored to the case that owns the defect.
run_case() {
  local label="$1" expr="$2" want="$3" text="$4"
  local copy out code changed
  n=$(( n + 1 ))
  copy="$WORK/case$n.conf.template"
  out="$WORK/case$n.out"
  sed -e "$expr" "$TEMPLATE" > "$copy"
  changed="$(diff "$TEMPLATE" "$copy" | grep -c '^<')"
  if [ -n "$expr" ] && [ "$changed" -ne 1 ]; then
    err "$label — the mutation changed $changed template lines, expected exactly 1"
    return
  fi
  scripts/check-gateway-brake.sh "$copy" > "$out" 2>&1
  code=$?
  if [ "$code" -ne "$want" ]; then
    err "$label — exited $code, expected $want"
    sed 's/^/        /' "$out"
  elif [ -n "$text" ] && ! grep 'FAIL' "$out" | grep -qE -- "$text"; then
    err "$label — exited $code as expected, but no FAIL line says: $text"
    sed 's/^/        /' "$out"
  elif [ -z "$text" ] && grep -q 'FAIL' "$out"; then
    err "$label — exited 0 yet printed a FAIL line"
    sed 's/^/        /' "$out"
  else
    ok "$label"
  fi
}

run_case "baseline: the repository's template passes every case" "" 0 ""

run_case "MUTATION room limit_req removed — nothing refuses a room flood" \
  '/^    limit_req zone=visio_mint_room burst=/d' \
  1 "room: 200-request burst from one client: only"

run_case "MUTATION every peer trusted — a stranger picks its own bucket" \
  's|^    set_real_ip_from .*|    set_real_ip_from 0.0.0.0/0;|' \
  1 "a peer outside the proxy tier cannot choose its key with X-Forwarded-For: only"

run_case "MUTATION real_ip_header dropped — every client keyed on the proxy" \
  '/^    real_ip_header X-Forwarded-For;$/d' \
  1 "room: another client behind the same proxy:"

# shellcheck disable=SC2016  # a literal regex in the template, not shell
run_case "MUTATION the room map counts Django's 301 hop — every join billed twice" \
  's|rooms/\[^/\]+/\$"|rooms/[^/]+/?$"|' \
  1 "room: a venue"

run_case "MUTATION lobby rate under a full room — a waiting room is refused" \
  's|rate=30r/s;|rate=10r/s;|' \
  1 "lobby: a full room of 30 polling"

run_case "MUTATION refusals answered 503 — neither admitted nor counted as refused" \
  's|^    limit_req_status 429;|    limit_req_status 503;|' \
  1 "room: 200-request burst from one client: [0-9]+ answers of 200, [0-9]+ neither 429 nor 502"

run_case "MUTATION room rate widened to 20 r/s — a burst looks the same, minting does not" \
  's|rate=2r/s;|rate=20r/s;|' \
  1 "room: rate held at 2 r/s once the bucket is full:"

run_case "MUTATION lobby rate widened to 90 r/s — three full rooms' worth" \
  's|rate=30r/s;|rate=90r/s;|' \
  1 "lobby: rate held at 30 r/s once the bucket is full:"

echo
declared="$(grep -c '^run_case ' "$0")"
if [ "$n" -ne "$declared" ]; then
  err "ran $n cases of the $declared this file declares"
fi
FINISHED=1
if [ "$rc" -eq 0 ]; then
  echo "Every gateway brake verdict can fail, and names its cause ($n cases)."
else
  echo "Gateway brake self-test FAILED — a verdict no longer fires or misnames its cause."
fi
exit "$rc"
