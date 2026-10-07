#!/usr/bin/env bash
# Self-test for two assertions in check-upstream-contract.sh: the lobby-poll
# one — the one there that compares a number rather than matching a string,
# and so the one whose threshold can drift without anyone seeing it — and the
# sign-in one, the only one that reads a file of this repo (theme/custom.css)
# against an upstream file, so the one an edit here can break.
#
# Each case writes a useLobby.ts line, runs that assertion alone
# (`--lobby-poll`), and asserts the exit status AND the message: the exit
# status because it is all CI consumes, the message because it names the
# value read — a pass that read the wrong number has only happened to pass.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

WORK="$(mktemp -d)"
FINISHED=0
# Anything that ends this script before its verdict must not exit 0.
trap 'rm -rf "$WORK"; [ "$FINISHED" = 1 ] || { echo "upstream contract self-test ABORTED before its verdict — nothing was proven"; exit 1; }' EXIT

rc=0
n=0
ok()  { printf '  \033[32mok\033[0m   %s\n' "$1"; }
err() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }

echo "Upstream contract self-test — the lobby-poll threshold and the hidden sign-in, both directions"
echo

# run_case <label> <useLobby.ts line> <expected exit> <text on the PASS or FAIL line>
run_case() {
  local label="$1" line="$2" want="$3" text="$4" file out code verdict
  n=$(( n + 1 ))
  file="$WORK/useLobby.$n.ts"
  printf '%s\n' "$line" > "$file"
  out="$(scripts/check-upstream-contract.sh --lobby-poll "$file" 2>&1)"
  code=$?
  verdict=PASS
  [ "$want" -ne 0 ] && verdict=FAIL
  if [ "$code" -ne "$want" ]; then
    err "$label — exited $code, expected $want"
    printf '%s\n' "$out" | sed 's/^/        /'
  elif ! printf '%s\n' "$out" | grep "$verdict" | grep -qF -- "$text"; then
    err "$label — exited $code as expected, but no $verdict line says: $text"
    printf '%s\n' "$out" | sed 's/^/        /'
  else
    ok "$label"
  fi
}

run_case "upstream main's pace, 3_000 ms — slower, so only more generous" \
  'export const POLL_INTERVAL_MS = 3_000' 0 "the lobby polls every 3000 ms, no faster"
run_case "the pace the brake was sized for, 1000 ms" \
  'export const POLL_INTERVAL_MS = 1000' 0 "the lobby polls every 1000 ms, no faster"
run_case "MUTATION 500 ms — twice the polls the lobby brake was sized for" \
  'export const POLL_INTERVAL_MS = 500' 1 "the lobby polls every 500 ms, faster than"
run_case "MUTATION the constant renamed — nothing left to compare" \
  'export const POLL_MS = 1000' 1 "no longer sets POLL_INTERVAL_MS to a number"

# run_login_case <label> <LoginButton.tsx file> <custom.css file> <expected exit> <text on the PASS or FAIL line>
run_login_case() {
  local label="$1" button="$2" css="$3" want="$4" text="$5" out code verdict
  n=$(( n + 1 ))
  out="$(scripts/check-upstream-contract.sh --login-hidden "$button" "$css" 2>&1)"
  code=$?
  verdict=PASS
  [ "$want" -ne 0 ] && verdict=FAIL
  if [ "$code" -ne "$want" ]; then
    err "$label — exited $code, expected $want"
    printf '%s\n' "$out" | sed 's/^/        /'
  elif ! printf '%s\n' "$out" | grep "$verdict" | grep -qF -- "$text"; then
    err "$label — exited $code as expected, but no $verdict line says: $text"
    printf '%s\n' "$out" | sed 's/^/        /'
  else
    ok "$label"
  fi
}

# The upstream line as v1.24.0 ships it, and one without the attribute.
printf '%s\n' '    <LinkButton href={authUrl()} data-attr="login" variant="primary">' > "$WORK/LoginButton.ts"
printf '%s\n' '    <LinkButton href={authUrl()} variant="primary">' > "$WORK/LoginButton.noattr.ts"
# The theme as committed, and three ways to lose its rule.
sed '/^a\[data-attr="login"\] {$/,/^}$/d' theme/custom.css > "$WORK/custom.norule.css"
sed '/^a\[data-attr="login"\] {$/,/^}$/s/display: none;/display: inline-flex;/' theme/custom.css > "$WORK/custom.shown.css"
sed 's/^a\[data-attr="login"\] {$/a[data-attr="logout"] {/' theme/custom.css > "$WORK/custom.otherattr.css"

run_login_case "the committed theme against the upstream button" \
  "$WORK/LoginButton.ts" theme/custom.css 0 'theme/custom.css hides them'
run_login_case "MUTATION the rule deleted from the theme" \
  "$WORK/LoginButton.ts" "$WORK/custom.norule.css" 1 'no longer hides a[data-attr="login"]'
run_login_case "MUTATION the rule kept but no longer display: none" \
  "$WORK/LoginButton.ts" "$WORK/custom.shown.css" 1 'no longer hides a[data-attr="login"]'
run_login_case "MUTATION the rule aimed at another attribute" \
  "$WORK/LoginButton.ts" "$WORK/custom.otherattr.css" 1 'no longer hides a[data-attr="login"]'
run_login_case "MUTATION upstream drops the attribute" \
  "$WORK/LoginButton.noattr.ts" theme/custom.css 1 'no longer tags its button data-attr="login"'

echo
declared="$(grep -cE '^run_(login_)?case ' "$0")"
if [ "$n" -ne "$declared" ]; then
  err "ran $n cases of the $declared this file declares"
fi
FINISHED=1
if [ "$rc" -eq 0 ]; then
  echo "The lobby-poll assertion passes a slower pace and fails a faster one, naming the value; the sign-in assertion fails when the theme or upstream loses the selector ($n cases)."
else
  echo "Upstream contract self-test FAILED — an assertion misjudges its input."
fi
exit "$rc"
