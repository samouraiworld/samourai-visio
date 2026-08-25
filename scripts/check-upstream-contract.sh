#!/usr/bin/env bash
# Assert that every upstream behaviour this repo's configuration depends on is
# still true. Each assertion corresponds to a verified upstream behaviour the
# config relies on (the July 2026 drift review) — if one fails, upstream moved
# and the affected config must be re-derived BEFORE deploying.
#
# Usage:  scripts/check-upstream-contract.sh [ref]
#         ref defaults to $UPSTREAM_REF, then to the pinned version.
#
# Exits non-zero on the first broken assumption.

set -uo pipefail

REF="${1:-${UPSTREAM_REF:-v1.24.0}}"
MEET="https://raw.githubusercontent.com/suitenumerique/meet/${REF}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fyi()  { printf '        %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=1; }

fetch() { # fetch <remote-path> <local-name>
  local code
  code=$(curl -sS -o "$WORK/$2" -w '%{http_code}' "$MEET/$1")
  [ "$code" = "200" ] || { bad "fetch $1 -> HTTP $code"; return 1; }
}

echo "Upstream contract — suitenumerique/meet@${REF}"
echo

fetch src/backend/meet/settings.py         settings.py    || exit 1
fetch env.d/production.dist/common         common         || exit 1
fetch docs/examples/compose/compose.yaml   compose.yaml   || exit 1
fetch src/frontend/panda.config.ts         panda.config.ts|| exit 1
fetch src/backend/core/api/viewsets.py     viewsets.py    || exit 1
fetch docker/files/production/default.conf.template gateway.conf || exit 1

# ── BLOCKER-1 · the runtime-CSS variable is FRONTEND_CUSTOM_CSS_URL ──────────
if grep -q 'environ_name="FRONTEND_CUSTOM_CSS_URL"' "$WORK/settings.py"; then
  pass "FRONTEND_CUSTOM_CSS_URL is still the runtime-CSS setting"
else
  bad "FRONTEND_CUSTOM_CSS_URL no longer found — theme delivery will break"
fi
if grep -q 'FRONTEND_CSS_URL' "$WORK/settings.py"; then
  bad "FRONTEND_CSS_URL now exists upstream — re-read docs/theming.md"
else
  pass "FRONTEND_CSS_URL still does not exist (a wrong name fails silently)"
fi

# ── Trap 1 · fullname default still contains the ProConnect-only claim ───────
if grep -A2 'OIDC_USERINFO_FULLNAME_FIELDS = values' "$WORK/settings.py" | grep -q 'usual_name'; then
  pass "Trap 1 live: default is still [given_name, usual_name] — override required"
else
  fyi "Trap 1 CHANGED: 'usual_name' is gone from the default."
  bad "Re-check whether OIDC_USERINFO_FULLNAME_FIELDS still needs overriding"
fi

# ── Trap 2 · scopes default is still too narrow for display names ────────────
if grep -A1 'OIDC_RP_SCOPES = values' "$WORK/settings.py" | grep -q '"openid email"'; then
  pass "Trap 2 live: scope default is still 'openid email' — 'profile' required"
else
  fyi "Trap 2 CHANGED: the OIDC_RP_SCOPES default is no longer 'openid email'."
  bad "Re-check whether the 'profile' scope is still needed"
fi

# ── Trap 3 · logout endpoint still defaults to None (unset is safe) ──────────
if grep -A1 'OIDC_OP_LOGOUT_ENDPOINT = values' "$WORK/settings.py" | grep -q 'None'; then
  pass "Trap 3 live: OIDC_OP_LOGOUT_ENDPOINT still defaults to None"
else
  bad "OIDC_OP_LOGOUT_ENDPOINT default changed — leaving it unset may no longer be safe"
fi

# ── Trap 4 · code default True, production template False ───────────────────
if grep -A1 'ALLOW_UNREGISTERED_ROOMS = values' "$WORK/settings.py" | grep -qE '\bTrue\b'; then
  pass "Trap 4a live: code default for ALLOW_UNREGISTERED_ROOMS is still True"
else
  bad "ALLOW_UNREGISTERED_ROOMS code default changed"
fi
if grep -q '^ALLOW_UNREGISTERED_ROOMS=False' "$WORK/common"; then
  pass "Trap 4b live: production template still ships False — must be flipped"
else
  bad "Production template no longer ships ALLOW_UNREGISTERED_ROOMS=False"
fi

# ── Every OIDC key we set must still be a recognised setting ────────────────
missing=""
for k in OIDC_CREATE_USER OIDC_USE_PKCE OIDC_PKCE_CODE_CHALLENGE_METHOD \
         OIDC_REDIRECT_REQUIRE_HTTPS OIDC_REDIRECT_ALLOWED_HOSTS \
         OIDC_USERINFO_FULLNAME_FIELDS OIDC_USERINFO_SHORTNAME_FIELD \
         OIDC_USERINFO_ESSENTIAL_CLAIMS OIDC_STORE_ID_TOKEN \
         OIDC_USE_NONCE LIVEKIT_FORCE_WSS_PROTOCOL; do
  grep -q "environ_name=\"$k\"" "$WORK/settings.py" || missing="$missing $k"
done
if [ -z "$missing" ]; then
  pass "every OIDC/LiveKit key we set is still a recognised setting"
else
  bad "settings no longer recognised (they would be ignored silently):$missing"
fi

# ── Panda tokens · no cssVar prefix, so our --colors-* names hold ────────────
if grep -qE '^\s*prefix\s*:' "$WORK/panda.config.ts"; then
  bad "panda.config.ts now sets a cssVar prefix — every token in theme/custom.css is wrong"
else
  pass "panda.config.ts sets no prefix — --colors-* / --fonts-* names hold"
fi
if grep -q 'primaryDark' "$WORK/panda.config.ts"; then
  pass "primaryDark ramp still present (in-room surface)"
else
  bad "primaryDark ramp gone — the dark-surface half of the theme is dead"
fi

# ── compose · our override merges with, and must not clobber, upstream ──────
if grep -q 'default.conf.template' "$WORK/compose.yaml"; then
  pass "frontend still mounts default.conf.template (override must merge, not replace)"
else
  bad "frontend no longer mounts default.conf.template — re-check compose.override.yaml"
fi

# ── compose · still ships floating tags, so pinning is still required ───────
if grep -q ':latest' "$WORK/compose.yaml"; then
  pass "upstream still ships :latest — compose.override.yaml pins are still required"
else
  fyi "upstream no longer ships :latest; our pins are now belt-and-braces."
fi

# ── Unregistered rooms stay unpersisted ─────────────────────────────────────
# The privacy policy states that rooms created without an account are never
# stored server-side (landing/confidentialite/). That holds only while the
# ALLOW_UNREGISTERED_ROOMS path keeps building its response in memory —
# id None, LiveKit token, no model write (viewsets.py:257-277 at v1.24.0).
# If upstream starts persisting them, the page is wrong the day the image is
# bumped, and a periodic purge becomes a real obligation.
SEG="$(sed -n '/Allow unregistered rooms when activated/,/def list/p' "$WORK/viewsets.py")"
if [ -z "$SEG" ]; then
  bad "cannot locate the unregistered-room path in viewsets.py — re-verify the privacy policy's 'never stored' claim"
elif echo "$SEG" | grep -q '"id": None' && ! echo "$SEG" | grep -qE '\.(create|save|get_or_create)\('; then
  pass "unregistered rooms are still synthetic (id None, no model write) — the 'never stored' claim holds"
else
  bad "the unregistered-room path changed and may now persist rooms — the privacy policy's 'never stored' claim must be re-verified"
fi

# ── Gateway template: our copy must equal upstream's, marked blocks aside ───
# deploy/nginx/default.conf.template replaces the upstream-fetched gateway
# (same compose mount target) to 301 the SPA's hardcoded DINUM legal routes
# to our own pages. It has to stay a verbatim copy otherwise, or gateway
# drift ships silently on the next image bump. diff -B: blank-line noise
# left by stripping the markers is not drift.
OURS="$(dirname "$0")/../deploy/nginx/default.conf.template"
if [ ! -f "$OURS" ]; then
  bad "deploy/nginx/default.conf.template is missing while compose.override.yaml mounts it"
elif sed '/# SAMOURAI-BEGIN/,/# SAMOURAI-END/d' "$OURS" | diff -B -q - "$WORK/gateway.conf" >/dev/null 2>&1; then
  pass "gateway override is upstream's template plus only the SAMOURAI-marked blocks"
else
  bad "gateway template drifted from upstream at ${REF} — re-derive deploy/nginx/default.conf.template (fresh upstream copy + the marked blocks)"
fi

# ── LiveKit: the room-cap keys must exist at the pinned server tag ──────────
# The only caps this stack has are LiveKit's server-level room settings
# (deploy/livekit-server.yaml.example) — Meet has none, and a renamed key
# would be ignored silently, evaporating the cap. The tag is read from the
# compose pin so this check cannot go stale against it.
LK_REF="$(grep -oE 'livekit/livekit-server:v[0-9.]+' "$(dirname "$0")/../deploy/compose.override.yaml" | head -1 | cut -d: -f2)"
if [ -z "$LK_REF" ]; then
  bad "cannot read the pinned livekit tag from deploy/compose.override.yaml"
else
  lkcode=$(curl -sS -o "$WORK/lk-config.go" -w '%{http_code}' "https://raw.githubusercontent.com/livekit/livekit/${LK_REF}/pkg/config/config.go")
  if [ "$lkcode" != "200" ]; then
    bad "fetch livekit pkg/config/config.go @ ${LK_REF} -> HTTP $lkcode"
  else
    lkmiss=""
    for k in auto_create max_participants empty_timeout departure_timeout; do
      grep -q "yaml:\"$k" "$WORK/lk-config.go" || lkmiss="$lkmiss $k"
    done
    if [ -z "$lkmiss" ]; then
      pass "livekit ${LK_REF} still recognises the room-cap keys we set (and auto_create, which the guest flow needs)"
    else
      bad "livekit room-config keys missing at ${LK_REF}:$lkmiss — they would be ignored silently"
    fi
  fi
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "All upstream assumptions hold at ${REF}."
else
  echo "BROKEN ASSUMPTIONS at ${REF}. Re-run the drift analysis before deploying."
fi
exit "$fail"
