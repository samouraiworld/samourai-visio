#!/usr/bin/env bash
# Self-test for the assertions in check-upstream-contract.sh that read a
# number or a file of this repo: the lobby-poll one — the one there that
# compares a number rather than matching a string, and so the one whose
# threshold can drift without anyone seeing it — the sign-in one, the only one
# that reads a file of this repo (theme/custom.css) against an upstream file,
# so the one an edit here can break — the silent-login and closed-OIDC ones
# over this repository's two deployments, and the advisory count of the SPA's
# sign-in entry points.
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

echo "Upstream contract self-test — the lobby-poll threshold, the hidden sign-in, silent login off, OIDC closed and the sign-in entry count, both directions"
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

# The upstream line as v1.24.0 ships it, one without the attribute, and one
# where the attribute survives only in a comment.
printf '%s\n' '    <LinkButton href={authUrl()} data-attr="login" variant="primary">' > "$WORK/LoginButton.ts"
printf '%s\n' '    <LinkButton href={authUrl()} variant="primary">' > "$WORK/LoginButton.noattr.ts"
printf '%s\n' '    // was: <LinkButton href={authUrl()} data-attr="login">' \
              '    <LinkButton href={authUrl()} variant="primary">' > "$WORK/LoginButton.comment.ts"
printf '%s\n' '    {/* <LinkButton href={authUrl()} data-attr="login"> */}' \
              '    <LinkButton href={authUrl()} variant="primary">' > "$WORK/LoginButton.jsxcomment.ts"
printf '%s\n' "    const attr = 'data-attr=\"login\" variant'" \
              '    <LinkButton href={authUrl()} variant="primary">' > "$WORK/LoginButton.notag.ts"
# The theme as committed, and every way to lose its rule that a line grep
# would miss: deleted, shown, retargeted, tied to <a> again, commented out,
# overridden by a later rule, or emptied with display: none in the next rule.
rule='/^\[data-attr="login"\] {$/,/^}$/'
sed "${rule}d" theme/custom.css > "$WORK/custom.norule.css"
sed "${rule}s/display: none;/display: inline-flex;/" theme/custom.css > "$WORK/custom.shown.css"
sed 's/^\[data-attr="login"\] {$/[data-attr="logout"] {/' theme/custom.css > "$WORK/custom.otherattr.css"
sed 's/^\[data-attr="login"\] {$/a[data-attr="login"] {/' theme/custom.css > "$WORK/custom.anchor.css"
sed "${rule}{s|^\[|/* [|;s|^}$|} */|;}" theme/custom.css > "$WORK/custom.commented.css"
{ cat theme/custom.css; printf '%s\n' '[data-attr="login"] {' '  display: inline-flex;' '}'; } > "$WORK/custom.overridden.css"
sed "${rule}s/display: none;/color: inherit;/" theme/custom.css > "$WORK/custom.emptied.css"
printf '%s\n' '.next {' '  display: none;' '}' >> "$WORK/custom.emptied.css"
sed 's/^\[data-attr="login"\] {$/.selftest-other, [data-attr="login"] {/' theme/custom.css > "$WORK/custom.list.css"
# A sed that BSD rejects, or that matches nothing, leaves an empty or an
# unchanged mutant; its case would then prove nothing, or the wrong thing.
for f in "$WORK"/custom.*.css; do
  if [ ! -s "$f" ] || cmp -s theme/custom.css "$f"; then
    err "mutant $(basename "$f") is empty or equal to theme/custom.css — its case proves nothing"
  fi
done

run_login_case "the committed theme against the upstream button" \
  "$WORK/LoginButton.ts" theme/custom.css 0 'theme/custom.css hides them'
run_login_case "the rule as one selector of a list still hides the button" \
  "$WORK/LoginButton.ts" "$WORK/custom.list.css" 0 'theme/custom.css hides them'
run_login_case "MUTATION the rule deleted from the theme" \
  "$WORK/LoginButton.ts" "$WORK/custom.norule.css" 1 'no longer hides [data-attr="login"]'
run_login_case "MUTATION the rule kept but no longer display: none" \
  "$WORK/LoginButton.ts" "$WORK/custom.shown.css" 1 'no longer hides [data-attr="login"]'
run_login_case "MUTATION the rule aimed at another attribute" \
  "$WORK/LoginButton.ts" "$WORK/custom.otherattr.css" 1 'no longer hides [data-attr="login"]'
run_login_case "MUTATION the rule tied to <a> — misses a button that stops being a link" \
  "$WORK/LoginButton.ts" "$WORK/custom.anchor.css" 1 'no longer hides [data-attr="login"]'
run_login_case "MUTATION the rule commented out" \
  "$WORK/LoginButton.ts" "$WORK/custom.commented.css" 1 'no longer hides [data-attr="login"]'
run_login_case "MUTATION a later rule shows the button again" \
  "$WORK/LoginButton.ts" "$WORK/custom.overridden.css" 1 'no longer hides [data-attr="login"]'
run_login_case "MUTATION the rule emptied, display: none only in the next rule" \
  "$WORK/LoginButton.ts" "$WORK/custom.emptied.css" 1 'no longer hides [data-attr="login"]'
run_login_case "MUTATION upstream drops the attribute" \
  "$WORK/LoginButton.noattr.ts" theme/custom.css 1 'no longer tags its button data-attr="login"'
run_login_case "MUTATION upstream keeps the attribute only in a comment" \
  "$WORK/LoginButton.comment.ts" theme/custom.css 1 'no longer tags its button data-attr="login"'
run_login_case "MUTATION upstream keeps the attribute only in a JSX comment" \
  "$WORK/LoginButton.jsxcomment.ts" theme/custom.css 1 'no longer tags its button data-attr="login"'
run_login_case "MUTATION the attribute survives only outside a <Tag" \
  "$WORK/LoginButton.notag.ts" theme/custom.css 1 'no longer tags its button data-attr="login"'

# run_silent_case <label> <file content> <expected exit> <text on the PASS or FAIL line>
run_silent_case() {
  local label="$1" content="$2" want="$3" text="$4" file out code verdict
  n=$(( n + 1 ))
  file="$WORK/silent.$n"
  printf '%s\n' "$content" > "$file"
  out="$(scripts/check-upstream-contract.sh --silent-login-off "$file" 2>&1)"
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

run_silent_case "an env file turning silent login off" \
  'FRONTEND_IS_SILENT_LOGIN_ENABLED=false' 0 'turns silent login off'
run_silent_case "a compose file turning silent login off" \
  '      FRONTEND_IS_SILENT_LOGIN_ENABLED: "false"' 0 'turns silent login off'
run_silent_case "MUTATION the line commented out" \
  '#FRONTEND_IS_SILENT_LOGIN_ENABLED=false' 1 'does not set FRONTEND_IS_SILENT_LOGIN_ENABLED to false'
run_silent_case "MUTATION silent login turned on" \
  '      FRONTEND_IS_SILENT_LOGIN_ENABLED: "true"' 1 'does not set FRONTEND_IS_SILENT_LOGIN_ENABLED to false'
run_silent_case "MUTATION the setting missing — upstream's default is true" \
  'FRONTEND_CUSTOM_CSS_URL=/custom/style.css' 1 'does not set FRONTEND_IS_SILENT_LOGIN_ENABLED to false'
run_silent_case "MUTATION a later line turns it back on (Docker keeps the last)" \
  "$(printf '%s\n' 'FRONTEND_IS_SILENT_LOGIN_ENABLED=false' 'FRONTEND_IS_SILENT_LOGIN_ENABLED=true')" 1 'does not set FRONTEND_IS_SILENT_LOGIN_ENABLED to false'

# run_oidc_case <label> <file content> <expected exit> <text on the PASS or FAIL line>
run_oidc_case() {
  local label="$1" content="$2" want="$3" text="$4" file out code verdict
  n=$(( n + 1 ))
  file="$WORK/oidc.$n"
  printf '%s\n' "$content" > "$file"
  out="$(scripts/check-upstream-contract.sh --oidc-closed "$file" 2>&1)"
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

oidc_keys='OIDC_OP_JWKS_ENDPOINT OIDC_OP_AUTHORIZATION_ENDPOINT OIDC_OP_TOKEN_ENDPOINT OIDC_OP_USER_ENDPOINT OIDC_RP_CLIENT_ID OIDC_RP_CLIENT_SECRET'
# shellcheck disable=SC2086  # the key list is split on purpose
env_closed="$(printf '%s=\n' $oidc_keys)"
# shellcheck disable=SC2086
yaml_closed="$(printf '      %s: ""\n' $oidc_keys)"
run_oidc_case "an env file with the six settings empty" \
  "$env_closed" 0 'names no identity provider'
run_oidc_case "a compose file with the six settings empty" \
  "$yaml_closed" 0 'names no identity provider'
run_oidc_case "MUTATION a provider endpoint set again" \
  "${env_closed/OIDC_OP_JWKS_ENDPOINT=/OIDC_OP_JWKS_ENDPOINT=https://clerk.samourai.app/.well-known/jwks.json}" 1 'still sets OIDC_OP_JWKS_ENDPOINT'
run_oidc_case "MUTATION a client ID set again in compose" \
  "${yaml_closed/OIDC_RP_CLIENT_ID: \"\"/OIDC_RP_CLIENT_ID: visio}" 1 'still sets OIDC_RP_CLIENT_ID'
run_oidc_case "MUTATION a YAML null instead of an empty string (compose passes the host's value)" \
  "${yaml_closed/OIDC_RP_CLIENT_SECRET: \"\"/OIDC_RP_CLIENT_SECRET:}" 1 'still sets OIDC_RP_CLIENT_SECRET'
run_oidc_case "MUTATION a later line sets the token endpoint again" \
  "$(printf '%s\n' "$env_closed" 'OIDC_OP_TOKEN_ENDPOINT=https://idp.example/token')" 1 'still sets OIDC_OP_TOKEN_ENDPOINT'
run_oidc_case "MUTATION a setting removed — unset fails every signed-in request" \
  "$(printf '%s\n' "$env_closed" | grep -v '^OIDC_OP_USER_ENDPOINT=')" 1 'no longer carries OIDC_OP_USER_ENDPOINT'

# run_authurl_case <label> <number of call sites> <PASS or NOTE> <text on that line>
# Advisory: it never fails, so the case asserts exit 0 and the line it prints.
run_authurl_case() {
  local label="$1" sites="$2" verdict="$3" text="$4" dir out code i
  n=$(( n + 1 ))
  dir="$WORK/authurl.$n/meet-x/src/frontend/src"
  mkdir -p "$dir"
  printf '%s\n' 'export const authUrl = () => "/api/v1.0/authenticate/"' \
                '// authUrl() in a comment does not count' > "$dir/auth.ts"
  for i in $(seq 1 "$sites"); do
    printf '%s\n' "    window.location.href = authUrl({})" > "$dir/site$i.tsx"
  done
  tar -czf "$WORK/authurl.$n.tar.gz" -C "$WORK/authurl.$n" meet-x
  out="$(scripts/check-upstream-contract.sh --authurl-sites "$WORK/authurl.$n.tar.gz" selftest 2>&1)"
  code=$?
  if [ "$code" -ne 0 ]; then
    err "$label — exited $code; an advisory must never fail"
    printf '%s\n' "$out" | sed 's/^/        /'
  elif ! printf '%s\n' "$out" | grep "$verdict" | grep -qF -- "$text"; then
    err "$label — no $verdict line says: $text"
    printf '%s\n' "$out" | sed 's/^/        /'
  else
    ok "$label"
  fi
}

run_authurl_case "four call sites, as the pinned release" \
  4 PASS 'the SPA starts a sign-in from 4 authUrl( call sites at selftest'
run_authurl_case "MUTATION a fifth call site (upstream main's SDK popup) — a NOTE, never a failure" \
  5 NOTE 'the SPA starts a sign-in from 5 authUrl( call sites at selftest, 4 at v1.24.0'

echo
declared="$(grep -cE '^run_((login|silent|oidc|authurl)_)?case ' "$0")"
if [ "$n" -ne "$declared" ]; then
  err "ran $n cases of the $declared this file declares"
fi
FINISHED=1
if [ "$rc" -eq 0 ]; then
  echo "The lobby-poll assertion passes a slower pace and fails a faster one, naming the value; the sign-in assertions fail when the theme or upstream loses the selector, silent login is left on, or a deployment names an identity provider; the entry-point count notes a new one ($n cases)."
else
  echo "Upstream contract self-test FAILED — an assertion misjudges its input."
fi
exit "$rc"
