#!/usr/bin/env bash
# Self-test for the assertions in check-upstream-contract.sh that read a
# number or a file of this repo: the lobby-poll one — the one there that
# compares a number rather than matching a string, and so the one whose
# threshold can drift without anyone seeing it — the silent-login one over
# this repository's two deployments, the realm pin of the host template, the
# closed sign-in of the Greffon package, and the advisory count of the SPA's
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

echo "Upstream contract self-test — the lobby-poll threshold, silent login off, the realm pin, the closed Greffon sign-in and the sign-in entry count, both directions"
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

# run_realm_case <label> <env file content> <expected exit> <text on the PASS or FAIL line>
run_realm_case() {
  local label="$1" content="$2" want="$3" text="$4" file out code verdict
  n=$(( n + 1 ))
  file="$WORK/realm.$n"
  printf '%s\n' "$content" > "$file"
  out="$(scripts/check-upstream-contract.sh --oidc-realm "$file" 2>&1)"
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

env_realm="$(grep -E '^OIDC_' deploy/env.d/common.example)"
run_realm_case "the committed host template" \
  "$env_realm" 0 'pins sign-in to realm samourai-app, client visio'
run_realm_case "MUTATION the JWKS endpoint of another realm (its tokens would be trusted)" \
  "${env_realm//realms\/samourai-app\/protocol\/openid-connect\/certs/realms/other-realm/protocol/openid-connect/certs}" 1 'does not pin OIDC_OP_JWKS_ENDPOINT'
run_realm_case "MUTATION the token endpoint on another host" \
  "${env_realm//https:\/\/auth.kodera.io\/realms\/samourai-app\/protocol\/openid-connect\/token/https://auth.example.org/realms/samourai-app/protocol/openid-connect/token}" 1 'does not pin OIDC_OP_TOKEN_ENDPOINT'
run_realm_case "MUTATION the logout endpoint removed (the Keycloak session would survive logout)" \
  "$(printf '%s\n' "$env_realm" | grep -v '^OIDC_OP_LOGOUT_ENDPOINT=')" 1 'no longer carries OIDC_OP_LOGOUT_ENDPOINT'
run_realm_case "MUTATION the ID token no longer kept (no id_token_hint for logout)" \
  "${env_realm/OIDC_STORE_ID_TOKEN=true/OIDC_STORE_ID_TOKEN=false}" 1 'does not pin OIDC_STORE_ID_TOKEN'
run_realm_case "MUTATION another client id" \
  "${env_realm/OIDC_RP_CLIENT_ID=visio/OIDC_RP_CLIENT_ID=visio-test}" 1 'does not pin OIDC_RP_CLIENT_ID'
run_realm_case "MUTATION a real-looking secret in the public template" \
  "$(printf '%s\n' "$env_realm" | sed 's/^OIDC_RP_CLIENT_SECRET=.*/OIDC_RP_CLIENT_SECRET=s3cr3t-from-keycloak/')" 1 'carries a value for OIDC_RP_CLIENT_SECRET'
run_realm_case "MUTATION a later line moves the userinfo endpoint (Docker keeps the last)" \
  "$(printf '%s\n' "$env_realm" 'OIDC_OP_USER_ENDPOINT=https://idp.example/userinfo')" 1 'does not pin OIDC_OP_USER_ENDPOINT'

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
declared="$(grep -cE '^run_((silent|oidc|realm|authurl)_)?case ' "$0")"
if [ "$n" -ne "$declared" ]; then
  err "ran $n cases of the $declared this file declares"
fi
FINISHED=1
if [ "$rc" -eq 0 ]; then
  echo "The lobby-poll assertion passes a slower pace and fails a faster one, naming the value; the sign-in assertions fail when silent login is left on, the host template leaves realm samourai-app or carries a secret, or the Greffon package names an identity provider; the entry-point count notes a new one ($n cases)."
else
  echo "Upstream contract self-test FAILED — an assertion misjudges its input."
fi
exit "$rc"
