#!/usr/bin/env bash
# Self-test for preflight.sh `config` phase.
#
# The entire premise of preflight is that its checks can FAIL when the thing
# they test is broken. This proves it: build a good fixture, assert it passes,
# then mutate one thing at a time and assert the matching check flips to FAIL.
# If a mutation stops tripping its check, preflight has silently rotted into
# the very thing it exists to prevent — a check that always passes.
#
# Runs in CI. Needs docker compose (for the merge/pinning checks) and the repo
# templates; no host, no secrets, no network beyond fetching upstream compose.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

WORK="$(mktemp -d)"
# Inlined rather than a named function: shellcheck flags an unreachable trap
# body (SC2317/SC2329) differently across versions, and this avoids both.
trap 'chmod -R u+w "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT

export VISIO_DIR="$WORK"
rc=0
ok()  { printf '  \033[32mok\033[0m   %s\n' "$1"; }
err() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }

# ── Build a fixture that should pass every config check ─────────────────────
curl -sSf -o "$WORK/compose.yaml" \
  "https://raw.githubusercontent.com/suitenumerique/meet/${UPSTREAM_REF:-v1.24.0}/docs/examples/compose/compose.yaml" \
  || { echo "cannot fetch upstream compose"; exit 1; }
cp deploy/compose.override.yaml "$WORK/compose.override.yaml"
cp deploy/hosts.example "$WORK/.env"
mkdir -p "$WORK/env.d" "$WORK/custom" "$WORK/landing"

# Replace <placeholders> with well-formed, single-line fake values. The same
# token replaces the LiveKit secret in both files, so they match.
FAKE="selftest_fake_value_0000000000000000000000"
sed -E "s/<[^>]*>/$FAKE/g" deploy/env.d/common.example      > "$WORK/env.d/common"
sed -E "s/<[^>]*>/$FAKE/g" deploy/env.d/postgresql.example  > "$WORK/env.d/postgresql"
sed -E "s/<[^>]*>/$FAKE/"  deploy/livekit-server.yaml.example > "$WORK/livekit-server.yaml"
printf 'body\n' > "$WORK/custom/style.css"
printf 'png\n'  > "$WORK/custom/logo.png"
printf '<html></html>\n' > "$WORK/landing/index.html"
chmod 600 "$WORK/.env" "$WORK/env.d/common" "$WORK/env.d/postgresql"

fails() { bash scripts/preflight.sh config 2>/dev/null | grep -c 'FAIL'; }

echo "baseline: the good fixture must pass cleanly"
n="$(fails)"
if [ "$n" -eq 0 ]; then ok "good fixture: 0 failures"; else
  err "good fixture reported $n failure(s) — the fixture or a check is wrong"
  bash scripts/preflight.sh config 2>/dev/null | grep FAIL
fi

# ── mutate <sed-expr> <file> <label>: assert failures increase, then revert ──
mutate() {
  local expr="$1" file="$2" label="$3"
  cp "$WORK/$file" "$WORK/$file.orig"
  sed -i.bak "$expr" "$WORK/$file"
  local n; n="$(fails)"
  if [ "$n" -ge 1 ]; then ok "detected: $label"; else err "NOT detected: $label"; fi
  mv "$WORK/$file.orig" "$WORK/$file"; rm -f "$WORK/$file.bak"
}

echo "mutations: each must be caught"
mutate 's/^OIDC_USERINFO_FULLNAME_FIELDS=.*/OIDC_USERINFO_FULLNAME_FIELDS=["a","b"]/' env.d/common "JSON-shaped list value"
mutate 's/^LIVEKIT_API_SECRET=.*/LIVEKIT_API_SECRET=mismatch_000000000000000000000000000000/' env.d/common "LiveKit secret mismatch"
mutate 's/^FRONTEND_CUSTOM_CSS_URL=/FRONTEND_CSS_URL=/' env.d/common "wrong CSS variable name"
mutate 's/^DJANGO_SECRET_KEY=.*/DJANGO_SECRET_KEY=<openssl rand -base64 64>/' env.d/common "unfilled placeholder"
mutate 's/^OIDC_OP_TOKEN_ENDPOINT=/OIDC_OP_LOGOUT_ENDPOINT=https:\/\/x\/logout\nOIDC_OP_TOKEN_ENDPOINT=/' env.d/common "Keycloak-style logout endpoint present"
mutate 's/^  tls_port: 0/  tls_port: 5349/' livekit-server.yaml "TURN without tls_port: 0"
mutate 's|^FRONTEND_EXTERNAL_HOME_URL="\(.*\)/"|FRONTEND_EXTERNAL_HOME_URL="\1"|' env.d/common "landing URL without trailing slash"
mutate 's/^DJANGO_LANGUAGE_CODE=.*/DJANGO_LANGUAGE_CODE=fr/' env.d/common "unsupported language code"
mutate 's/^DJANGO_LANGUAGE_CODE=.*/#DJANGO_LANGUAGE_CODE=fr-fr/' env.d/common "language left at the English default"
mutate '\|/usr/share/nginx/html/accueil|d' compose.override.yaml "landing bind-mount dropped from the override"

# A malformed (wrapped-secret-style) line: a bare continuation with no '='.
echo "special: wrapped-secret continuation line"
cp "$WORK/env.d/common" "$WORK/env.d/common.orig"
printf '\nO3KoFX3uJTZ09L7Senb8WAzzzz\n' >> "$WORK/env.d/common"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: malformed env line"; else err "NOT detected: malformed env line"; fi
mv "$WORK/env.d/common.orig" "$WORK/env.d/common"

# Missing branding asset (Docker would mount a directory in its place).
echo "special: missing branding asset"
mv "$WORK/custom/style.css" "$WORK/custom/style.css.hidden"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: missing branding asset"; else err "NOT detected: missing branding asset"; fi
mv "$WORK/custom/style.css.hidden" "$WORK/custom/style.css"

# Landing page configured but absent — the mount Docker would fake as a
# directory, sending every anonymous visitor to the SPA fallback.
echo "special: landing page missing"
mv "$WORK/landing/index.html" "$WORK/landing/index.html.hidden"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: landing page missing"; else err "NOT detected: landing page missing"; fi
mv "$WORK/landing/index.html.hidden" "$WORK/landing/index.html"

# World-readable secret file.
echo "special: world-readable secret file"
chmod 644 "$WORK/env.d/common"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: world-readable secret"; else err "NOT detected: world-readable secret"; fi
chmod 600 "$WORK/env.d/common"

# Final: fixture is clean again, proving every revert worked.
echo "final: fixture restored"
n="$(fails)"
if [ "$n" -eq 0 ]; then ok "0 failures after all reverts"; else err "fixture not clean after reverts ($n)"; fi

echo
if [ "$rc" -eq 0 ]; then echo "preflight self-test passed: every check can still fail."
else echo "preflight self-test FAILED: a check no longer detects its defect."; fi
exit "$rc"
