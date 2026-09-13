#!/usr/bin/env bash
# Self-test for preflight.sh: the `config` phase against a fixture on disk,
# and the `edge` phase (the response-header subset of `public`) against a
# local HTTP stub.
#
# The entire premise of preflight is that its checks can FAIL when the thing
# they test is broken. This proves it: build a good fixture, assert it passes,
# then mutate one thing at a time and assert the matching check flips to FAIL.
# If a mutation stops tripping its check, preflight has silently rotted into
# the very thing it exists to prevent — a check that always passes.
#
# Runs in CI. Needs the repo templates and python3 (for the stub); no host,
# no secrets, no network beyond fetching upstream compose.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

WORK="$(mktemp -d)"
STUB_PID=""
FINISHED=0
# Inlined rather than a named function: shellcheck flags an unreachable trap
# body (SC2317/SC2329) differently across versions, and this avoids both.
#
# The last clause is the harness's own guard. Anything that ends this script
# before the verdict at the bottom — an `exit` in a fixture step, a helper
# that aborts — would otherwise leave whatever status the shell last had, and
# a run that proved nothing could exit 0. It exits 1 instead, and says so.
trap '[ -n "$STUB_PID" ] && kill "$STUB_PID" 2>/dev/null; chmod -R u+w "$WORK" 2>/dev/null; rm -rf "$WORK"; [ "$FINISHED" = 1 ] || { echo "preflight self-test ABORTED before its verdict — nothing was proven"; exit 1; }' EXIT

export VISIO_DIR="$WORK"
rc=0
# Every mutation helper counts the cases it runs, and the verdict compares
# that count with the helper calls written in this file. A section skipped by
# a branch, or a helper that returns before its assertion, cannot then pass
# by simply not happening.
cases=0
ok()  { printf '  \033[32mok\033[0m   %s\n' "$1"; }
err() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }

# ── Build a fixture that should pass every config check ─────────────────────
curl -sSf -o "$WORK/compose.yaml" \
  "https://raw.githubusercontent.com/suitenumerique/meet/${UPSTREAM_REF:-v1.24.0}/docs/examples/compose/compose.yaml" \
  || { echo "cannot fetch upstream compose"; exit 1; }
cp deploy/compose.override.yaml "$WORK/compose.override.yaml"
cp deploy/hosts.example "$WORK/.env"
# The one placeholder in the hosts template: the proxy tier's subnet, which
# only the host can supply. A documentation range (RFC 5737) stands in for it.
sed -i.bak 's|^PROXY_TIER_SUBNET=<[^>]*>$|PROXY_TIER_SUBNET=192.0.2.0/24|' "$WORK/.env" && rm -f "$WORK/.env.bak"
mkdir -p "$WORK/env.d" "$WORK/custom" "$WORK/landing" "$WORK/nginx"
# The shipped gateway copy must itself satisfy the redirect check.
cp deploy/nginx/default.conf.template "$WORK/nginx/default.conf.template"

# Replace <placeholders> with well-formed, single-line fake values. The same
# token replaces the LiveKit secret in both files, so they match.
FAKE="selftest_fake_value_0000000000000000000000"
sed -E "s/<[^>]*>/$FAKE/g" deploy/env.d/common.example      > "$WORK/env.d/common"
sed -E "s/<[^>]*>/$FAKE/g" deploy/env.d/postgresql.example  > "$WORK/env.d/postgresql"
sed -E "s/<[^>]*>/$FAKE/g" deploy/env.d/backup.example      > "$WORK/env.d/backup"
# The two backup keys must differ, as the check demands; the blanket
# placeholder replacement above would have made them identical.
sed -i.bak "s/^RCLONE_CONFIG_VISIOPRUNE_ACCESS_KEY_ID=.*/RCLONE_CONFIG_VISIOPRUNE_ACCESS_KEY_ID=${FAKE}_prune/" \
  "$WORK/env.d/backup" && rm -f "$WORK/env.d/backup.bak"
sed -E "s/<[^>]*>/$FAKE/"  deploy/livekit-server.yaml.example > "$WORK/livekit-server.yaml"
printf 'body\n' > "$WORK/custom/style.css"
printf 'png\n'  > "$WORK/custom/logo.png"
# The icon set the frontend mounts per file (copied from the repo, as §7 says).
mkdir -p "$WORK/custom/icons" && cp theme/icons/* "$WORK/custom/icons/"
printf '<html></html>\n' > "$WORK/landing/index.html"
chmod 600 "$WORK/.env" "$WORK/env.d/common" "$WORK/env.d/postgresql" "$WORK/env.d/backup"

# Host-side log-retention files, reached through VISIO_ETC. Copying the SHIPPED
# files doubles as an assertion that what deploy/host/ carries actually passes
# the checks. The rsyslog logrotate is fabricated in its tightened form (the
# check must pass on daily/7 and fail on the distro default of weekly/4).
mkdir -p "$WORK/etc/systemd/journald.conf.d" "$WORK/etc/docker" "$WORK/etc/logrotate.d" \
         "$WORK/etc/cron.d"
cp deploy/host/visio-retention.conf "$WORK/etc/systemd/journald.conf.d/visio-retention.conf"
cp deploy/host/daemon.json          "$WORK/etc/docker/daemon.json"
printf '/var/log/syslog\n/var/log/auth.log\n{\n\trotate 7\n\tdaily\n\tmissingok\n}\n' \
  > "$WORK/etc/logrotate.d/rsyslog"
# An installed backup cron, path-edited the way RUNBOOK §8ter prescribes:
# the dump line and the prune line.
printf '17 3 * * * user VISIO_DIR=/home/user/visio /home/user/repo/scripts/backup.sh 2>&1 | logger -t visio-backup\n45 3 * * * user VISIO_DIR=/home/user/visio /home/user/repo/scripts/backup.sh prune 2>&1 | logger -t visio-backup\n' \
  > "$WORK/etc/cron.d/visio-backup"
export VISIO_ETC="$WORK/etc"

fails() { bash scripts/preflight.sh config 2>/dev/null | grep -c 'FAIL'; }

# clean <phase> <label> [VAR=value ...]: the phase prints no FAIL line AND
# exits 0. A clean baseline is what gives every mutation below its meaning: on
# a fixture that already fails, any check looks caught.
clean() {
  local phase="$1" label="$2" out code
  shift 2
  out="$(env "$@" bash scripts/preflight.sh "$phase" 2>/dev/null)"
  code=$?
  if [ "$code" -eq 0 ] && ! printf '%s\n' "$out" | grep -q 'FAIL'; then
    ok "$label: 0 failures, exit 0"
  else
    err "$label: exit $code, $(printf '%s\n' "$out" | grep -c 'FAIL') failure(s) — the fixture or a check is wrong"
    printf '%s\n' "$out" | grep FAIL
  fi
}

echo "baseline: the good fixture must pass cleanly"
clean config "good fixture"

# ── mutate <sed-expr> <file> <label>: assert failures increase, then revert ──
mutate() {
  local expr="$1" file="$2" label="$3"
  cases=$((cases+1))
  cp "$WORK/$file" "$WORK/$file.orig"
  sed -i.bak "$expr" "$WORK/$file"
  local n; n="$(fails)"
  if [ "$n" -ge 1 ]; then ok "detected: $label"; else err "NOT detected: $label"; fi
  mv "$WORK/$file.orig" "$WORK/$file"; rm -f "$WORK/$file.bak"
}

# ── mutate_re: same, but assert the FAIL *text* matches ─────────────────────
# `mutate` credits any FAIL, so an unrelated breakage can vouch for a check
# that never fired. These two target one service key each in a file the other
# checks also read, so they assert on the message their own check emits.
mutate_re() {
  local expr="$1" file="$2" re="$3" label="$4"
  cases=$((cases+1))
  cp "$WORK/$file" "$WORK/$file.orig"
  sed -i.bak "$expr" "$WORK/$file"
  local hit
  hit="$(bash scripts/preflight.sh config 2>/dev/null | grep 'FAIL' | grep -c "$re")"
  if [ "$hit" -ge 1 ]; then ok "detected: $label"; else err "NOT detected: $label"; fi
  mv "$WORK/$file.orig" "$WORK/$file"; rm -f "$WORK/$file.bak"
}

# ── mutate_rs: the FAIL text AND preflight's exit status ────────────────────
# mutate_re proves the right check spoke. CI and an operator consume only the
# exit status, though, so a check that printed its FAIL line while the script
# still exited 0 would pass mutate_re and gate nothing. And a sed that matched
# nothing leaves the fixture as it was: that is reported as a case that did
# not run, never credited as a detection. Text is matched as a fixed string.
mutate_rs() {
  local expr="$1" file="$2" text="$3" label="$4" out code
  cases=$((cases+1))
  cp "$WORK/$file" "$WORK/$file.orig"
  sed -i.bak "$expr" "$WORK/$file"
  if cmp -s "$WORK/$file" "$WORK/$file.orig"; then
    err "NOT exercised: $label — the mutation changed nothing in $file"
  else
    out="$(bash scripts/preflight.sh config 2>/dev/null)"
    code=$?
    if [ "$code" -eq 0 ]; then
      err "NOT detected: $label — preflight exited 0"
    elif ! printf '%s\n' "$out" | grep 'FAIL' | grep -qF -- "$text"; then
      err "NOT detected: $label — exited $code, but no FAIL line says: $text"
    else
      ok "detected: $label"
    fi
  fi
  mv "$WORK/$file.orig" "$WORK/$file"; rm -f "$WORK/$file.bak"
}

echo "mutations: each must be caught"
mutate 's/^OIDC_USERINFO_FULLNAME_FIELDS=.*/OIDC_USERINFO_FULLNAME_FIELDS=["a","b"]/' env.d/common "JSON-shaped list value"
mutate 's/^LIVEKIT_API_SECRET=.*/LIVEKIT_API_SECRET=mismatch_000000000000000000000000000000/' env.d/common "LiveKit secret mismatch"
mutate 's/^FRONTEND_CUSTOM_CSS_URL=/FRONTEND_CSS_URL=/' env.d/common "wrong CSS variable name"
mutate 's|^#DJANGO_SENTRY_DSN=.*|SENTRY_DSN=https://k@sentry.example/1|' env.d/common "Sentry DSN under the bare name that resolves to None"
mutate 's/^DJANGO_SECRET_KEY=.*/DJANGO_SECRET_KEY=<openssl rand -base64 64>/' env.d/common "unfilled placeholder"
mutate 's/^OIDC_OP_TOKEN_ENDPOINT=/OIDC_OP_LOGOUT_ENDPOINT=https:\/\/x\/logout\nOIDC_OP_TOKEN_ENDPOINT=/' env.d/common "Keycloak-style logout endpoint present"
mutate 's/^  tls_port: 0/  tls_port: 5349/' livekit-server.yaml "TURN without tls_port: 0"
mutate 's/^  max_participants: 30/  max_participants: 0/' livekit-server.yaml "participant cap removed (0 = unlimited)"
mutate 's/^  max_participants: 30/  max_participants:/' livekit-server.yaml "participant cap key present but empty"
mutate 's/daily/monthly/' etc/logrotate.d/rsyslog "rsyslog rotating monthly (slipped past the old blacklist)"
mutate 's/^\trotate 7/\trotate 30/' etc/logrotate.d/rsyslog "rsyslog keeping 30 copies (slipped past the old blacklist)"
mutate 's/^  empty_timeout: 300/#  empty_timeout: 300/' livekit-server.yaml "empty-room timeout dropped"
mutate 's|^FRONTEND_EXTERNAL_HOME_URL="\(.*\)/"|FRONTEND_EXTERNAL_HOME_URL="\1"|' env.d/common "landing URL without trailing slash"
mutate 's/^DJANGO_LANGUAGE_CODE=.*/DJANGO_LANGUAGE_CODE=fr/' env.d/common "unsupported language code"
mutate 's/^DJANGO_LANGUAGE_CODE=.*/#DJANGO_LANGUAGE_CODE=fr-fr/' env.d/common "language left at the English default"
mutate '\|/usr/share/nginx/html/accueil|d' compose.override.yaml "landing bind-mount dropped from the override"
# nginx-proxy's per-vhost HSTS. The two vhosts are asymmetric, so each
# direction is mutated separately: turning livekit's policy off is the
# regression this check exists to stop, and leaving the frontend's on
# restores the duplicate header the gateway template was written to end.
mutate_re 's|^      - "HSTS=max-age=31536000; includeSubDomains"|      - HSTS=off|' \
  compose.override.yaml 'livekit sets HSTS' \
  "livekit HSTS disabled (nginx-proxy is its only source — that vhost would ship no policy)"
mutate_re 's|^      - HSTS=off|      - "HSTS=max-age=31536000"|' \
  compose.override.yaml 'frontend does not set HSTS=off' \
  "frontend HSTS left on (a second header on top of the gateway's; the browser obeys the first)"

# The published "no audience measurement" claim. posthog-js ships in the SPA
# and only stays inert while these stay unset, so each one is mutated on.
mutate_re 's|^FRONTEND_CUSTOM_CSS_URL=/custom/style.css|FRONTEND_CUSTOM_CSS_URL=/custom/style.css\
FRONTEND_ANALYTICS={"posthog":{"key":"phc_selftest"}}|' \
  env.d/common 'third-party data collection is enabled' \
  "analytics key wired into the SPA (the privacy policy says there is none)"
mutate_re 's|^FRONTEND_CUSTOM_CSS_URL=/custom/style.css|FRONTEND_CUSTOM_CSS_URL=/custom/style.css\
SIGNUP_NEW_USER_TO_MARKETING_EMAIL=true|' \
  env.d/common 'third-party data collection is enabled' \
  "new users auto-enrolled into the marketing list (ships addresses to Brevo)"
mutate 's|^    location = /mentions-legales  .*|    location = /mentions-legales { return 404; }|' nginx/default.conf.template "a single DINUM legal route left unredirected"
mutate 's|^    location = /accessibilite/ .*||' nginx/default.conf.template "one DINUM route variant deleted outright"
mutate 's|^    location = /accueil {.*||' nginx/default.conf.template "slash-completion for /accueil removed (dead http://host:8080 redirect returns)"
mutate 's|^    location ~ \^/admin .*||' nginx/default.conf.template "admin 404 dropped from the gateway"
# shellcheck disable=SC2016  # literal nginx variable names inside a sed script
mutate 's|\$cookie_meet_sessionid|$cookie_sessionid|' nginx/default.conf.template "share-card redirect keyed on the wrong session cookie name"
mutate 's|^    add_header Content-Security-Policy .*||' nginx/default.conf.template "CSP frame-ancestors header dropped"
mutate 's|^        proxy_hide_header Strict-Transport-Security;||' nginx/default.conf.template "HSTS no longer hidden from upstream (the 60s policy would win)"
# The header set Django also emits. Each mutation targets one line of one
# scope, so the indentation anchors matter: 4 spaces is the server level, 8
# the proxy blocks, 12 the if-block inside `location = /`.
mutate_re 's|^        proxy_hide_header Referrer-Policy;||' nginx/default.conf.template \
  'proxy_hide_header short' "Django's Referrer-Policy no longer hidden (two values on /api; the browser takes the last)"
mutate_re 's|^        proxy_hide_header X-Content-Type-Options;||' nginx/default.conf.template \
  'proxy_hide_header short' "Django's X-Content-Type-Options no longer hidden (arrives twice on /api)"
mutate_re 's|^    add_header Referrer-Policy "same-origin"|    add_header Referrer-Policy "strict-origin-when-cross-origin"|' \
  nginx/default.conf.template 'Referrer-Policy is not same-origin' \
  "gateway Referrer-Policy loosened away from Django's value (with Django's copy hidden, the loose one is all that is left)"
mutate_re 's|^            add_header Strict-Transport-Security .*||' nginx/default.conf.template \
  'the / redirect drops' "HSTS dropped from the / redirect's if-block (the scope bug that shipped a bare 302)"
mutate_re 's|^            add_header Referrer-Policy "same-origin"|            add_header Referrer-Policy "no-referrer-when-downgrade"|' \
  nginx/default.conf.template "redirect's copy of these headers differs" \
  "the / redirect's Referrer-Policy copy edited on its own (one file, two policies)"
mutate_re 's|^        default_type text/plain;||' nginx/default.conf.template \
  'security.txt block incomplete' "security.txt without default_type (it would go out as the SPA's text/html)"
mutate_re 's|Contact: mailto:|Contact: |' nginx/default.conf.template \
  'security.txt block incomplete' "security.txt Contact no longer a mailto: URI"
mutate_re 's|^    location /\.well-known/ { return 404; }||' nginx/default.conf.template \
  'security.txt block incomplete' "the /.well-known/ 404 catch-all removed (the SPA shell answers any well-known path again)"
mutate '\|nginx/default.conf.template|d' compose.override.yaml "gateway mount dropped (upstream's template would silently mount instead)"
mutate 's/^MaxRetentionSec=7day/MaxRetentionSec=1month/' etc/systemd/journald.conf.d/visio-retention.conf "journal retention loosened beyond the published 7 days"
mutate 's/"log-driver": "journald"/"log-driver": "json-file"/' etc/docker/daemon.json "docker default log driver reverted to json-file"
mutate 's/driver: journald/driver: json-file/' compose.override.yaml "compose logging driver reverted to json-file"
mutate '/./d' custom/icons/site.webmanifest "one icon file empty (Docker would mount a directory; the manifest would be upstream's)"
mutate 's/daily/weekly/' etc/logrotate.d/rsyslog "rsyslog logrotate back at the distro default"
mutate 's/^BACKUP_REMOTE_PATH=.*/BACKUP_REMOTE_PATH=<bucket name>/' env.d/backup "backup bucket left as a placeholder"
mutate 's|backup\.sh|something-else.sh|' etc/cron.d/visio-backup "backup cron pointing at nothing"
# The credential split: each half lost on its own.
mutate_re '/backup\.sh prune/d' etc/cron.d/visio-backup 'no ACTIVE line running .backup.sh prune' \
  "prune line dropped from the cron (nothing deletes; retention turns red at KEEP+2 days)"
mutate_re "s/^RCLONE_CONFIG_VISIOPRUNE_ACCESS_KEY_ID=.*/RCLONE_CONFIG_VISIOPRUNE_ACCESS_KEY_ID=$FAKE/" env.d/backup \
  'same access key' "prune key set to the write key (one credential that writes and deletes)"
mutate_re '/^RCLONE_CONFIG_VISIOPRUNE_/d' env.d/backup 'no visioprune remote' \
  "visioprune block missing entirely (the prune has no credential)"

# ── The flood brake, and the proxy tier its key depends on ──────────────────
# mutate_rs throughout: the FAIL text AND a non-zero exit. Each text is what
# the owning check prints for the one piece this case breaks, so a case that a
# neighbouring check happens to catch is reported as not detected. Brackets
# and `$` are matched as [[] [$] so the same sed runs on GNU and BSD.
# shellcheck disable=SC2016  # literal nginx syntax inside a sed script
mutate_rs '/^limit_req_zone \$visio_mint_lobby_key /d' nginx/default.conf.template \
  'zone:lobby' "lobby zone removed (request-entry is no longer counted)"
mutate_rs 's|"~^POST |"~^GET |' nginx/default.conf.template \
  'map:request-entry' "lobby map counts GET instead of the POST that mints"
# shellcheck disable=SC2016  # literal nginx syntax inside a sed script
mutate_rs 's|rooms/[[]^/[]]+/[$]"|rooms/[^/]+/?$"|' nginx/default.conf.template \
  'map:room-detail' "room map widened to Django's 301 hop (every join billed twice)"
mutate_rs '/^    limit_req zone=visio_mint_room burst=/d' nginx/default.conf.template \
  'limit_req:room' "room brake counted but never applied"
mutate_rs 's|^    limit_req_status 429;|    limit_req_status 503;|' nginx/default.conf.template \
  'limit_req_status:429' "refusals answered 503 (the runbook's verification counts 429)"
# shellcheck disable=SC2016  # literal envsubst reference inside a sed script
mutate_rs 's|set_real_ip_from [$]{PROXY_TIER_SUBNET};|set_real_ip_from 0.0.0.0/0;|' nginx/default.conf.template \
  'set_real_ip_from:variable' "trusted proxy hardcoded as a catch-all instead of the host's subnet"
mutate_rs 's|^    real_ip_recursive off;|    real_ip_recursive off;\
    set_real_ip_from 0.0.0.0/0;|' nginx/default.conf.template \
  'set_real_ip_from:count' "a second, literal set_real_ip_from widening the trust"
mutate_rs 's|^    real_ip_recursive off;|    real_ip_recursive on;|' nginx/default.conf.template \
  'real_ip_recursive' "recursive realip (walks left into addresses a client wrote)"
# Sized against the room cap: each clause of that check broken alone.
mutate_rs 's/^  max_participants: 30/  max_participants: 45/' livekit-server.yaml \
  'lobby rate 30r/s is under a full room of 45' "room cap raised past the lobby brake (a full lobby would be refused)"
mutate_rs 's|zone=visio_mint_room burst=100 |zone=visio_mint_room burst=20 |' nginx/default.conf.template \
  'room burst 20 is under a full room of 30' "room burst under one full room joining at once"
mutate_rs 's|zone=visio_mint_room burst=100 |zone=visio_mint_room burst=250 |' nginx/default.conf.template \
  'room burst 250 lets a whole 200-request burst through' "room burst wide enough to admit the flood it exists for"
mutate_rs 's|zone=visio_mint_lobby burst=60 |zone=visio_mint_lobby burst=250 |' nginx/default.conf.template \
  'lobby burst 250 lets a whole 200-request burst through' "lobby burst wide enough to admit the flood it exists for"
# A widened rate admits the same first 101 of a burst, so no burst-shaped check
# sees it: only the upper bounds do.
mutate_rs 's|rate=2r/s;|rate=20r/s;|' nginx/default.conf.template \
  'room rate 20r/s is above 10r/s' "room rate widened tenfold (bursts unchanged, sustained minting ten times higher)"
mutate_rs 's|rate=30r/s;|rate=90r/s;|' nginx/default.conf.template \
  'lobby rate 90r/s is above two full rooms of 30' "lobby rate widened to three full rooms' polling"
# The subnet the host supplies.
mutate_rs '/^PROXY_TIER_SUBNET=/d' .env \
  'PROXY_TIER_SUBNET unset in .env' "proxy-tier subnet left unset"
mutate_rs 's|^PROXY_TIER_SUBNET=.*|PROXY_TIER_SUBNET=0.0.0.0/0|' .env \
  'PROXY_TIER_SUBNET=0.0.0.0/0 is a catch-all' "proxy-tier subnet set to the IPv4 catch-all"
mutate_rs 's|^PROXY_TIER_SUBNET=.*|PROXY_TIER_SUBNET=::/0|' .env \
  'PROXY_TIER_SUBNET=::/0 is a catch-all' "proxy-tier subnet set to the IPv6 catch-all"
mutate_rs 's|^PROXY_TIER_SUBNET=.*|PROXY_TIER_SUBNET=0.0.0.0/1|' .env \
  'PROXY_TIER_SUBNET=0.0.0.0/1 is a catch-all' "proxy-tier subnet wide enough to reach public space (not only /0)"
mutate_rs 's|^PROXY_TIER_SUBNET=.*|PROXY_TIER_SUBNET=proxy-tier|' .env \
  "PROXY_TIER_SUBNET='proxy-tier' is not a CIDR network" "proxy-tier subnet set to the network's name"
mutate_rs 's|^PROXY_TIER_SUBNET=.*|PROXY_TIER_SUBNET=192.0.2.1/24|' .env \
  "PROXY_TIER_SUBNET='192.0.2.1/24' is not a CIDR network" "proxy-tier subnet written as a host address with a prefix"
# shellcheck disable=SC2016  # literal compose interpolation inside a sed script
mutate_rs 's|[$]{PROXY_TIER_SUBNET:?[^}]*}|${PROXY_TIER_SUBNET:-0.0.0.0/0}|' compose.override.yaml \
  'does not refuse an unset PROXY_TIER_SUBNET' "compose given a default that trusts everyone instead of refusing"
mutate_rs '/- PROXY_TIER_SUBNET=/d' compose.override.yaml \
  "does not refuse an unset PROXY_TIER_SUBNET (frontend gets 'nothing')" "compose no longer passes the subnet with its refusal"

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

# World-readable backup credentials (the file carries S3 keys) — proves
# env.d/backup really is inside the shared permissions loop.
echo "special: world-readable backup credentials"
chmod 644 "$WORK/env.d/backup"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: world-readable backup credentials"; else err "NOT detected: world-readable backup credentials"; fi
chmod 600 "$WORK/env.d/backup"

# Backup cron never installed — the state of a host where the backup exists
# only as a script nobody scheduled.
echo "special: backup cron missing"
mv "$WORK/etc/cron.d/visio-backup" "$WORK/visio-backup.cron.hidden"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: backup cron missing"; else err "NOT detected: backup cron missing"; fi
mv "$WORK/visio-backup.cron.hidden" "$WORK/etc/cron.d/visio-backup"

# Gateway template file missing — Docker would mount a directory in its place
# and nginx would fail to start; the config phase must catch it before `up`.
echo "special: gateway template missing"
mv "$WORK/nginx/default.conf.template" "$WORK/nginx/default.conf.template.hidden"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: gateway template missing"; else err "NOT detected: gateway template missing"; fi
mv "$WORK/nginx/default.conf.template.hidden" "$WORK/nginx/default.conf.template"

# Journald retention drop-in missing entirely — the state of a host where
# RUNBOOK §8bis was never run, which is exactly what the check exists to catch.
echo "special: journald retention drop-in missing"
mv "$WORK/etc/systemd/journald.conf.d/visio-retention.conf" "$WORK/visio-retention.conf.hidden"
n="$(fails)"
if [ "$n" -ge 1 ]; then ok "detected: journald drop-in missing"; else err "NOT detected: journald drop-in missing"; fi
mv "$WORK/visio-retention.conf.hidden" "$WORK/etc/systemd/journald.conf.d/visio-retention.conf"

# Final: fixture is clean again, proving every revert worked.
echo "final: fixture restored"
n="$(fails)"
if [ "$n" -eq 0 ]; then ok "0 failures after all reverts"; else err "fixture not clean after reverts ($n)"; fi

# ── edge: the public response-header checks, against a local stub ───────────
# `preflight.sh public` runs against the live host, which a self-test must
# never mutate. Its header subset is reachable alone as the `edge` phase with
# VISIO_PUBLIC_ORIGIN pointed at this stub, whose MODE file breaks one thing
# per request — the same one-mutation-at-a-time shape as the fixture above.
# Good mode answers exactly what the gateway template is written to answer:
# a 302 on / with the four headers, /api with each header once, security.txt
# as text/plain with a future Expires, and a 404 for any other well-known path.
echo "edge: header checks against a local stub"
cat > "$WORK/stub.py" <<'PYSTUB'
import datetime, http.server, sys
MODE_FILE = sys.argv[1]


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def mode(self):
        try:
            return open(MODE_FILE).read().strip()
        except OSError:
            return ""

    def sec(self, hsts=True):
        if hsts:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")

    def body(self, code, ctype, data, extra=()):
        self.send_response(code)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.sec()
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        m = self.mode()
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/accueil/")
            self.send_header("Cache-Control", "no-store")
            self.sec(hsts=(m != "root-no-hsts"))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/api/v1.0/config/":
            extra = [("Referrer-Policy", "strict-origin-when-cross-origin")] if m == "api-dup-referrer" else []
            return self.body(200, "application/json", b"{}", extra)
        if self.path == "/.well-known/security.txt" and m != "securitytxt-missing":
            if m == "securitytxt-expired":
                exp = "2000-01-01T00:00:00Z"
            else:
                exp = (datetime.datetime.now(datetime.timezone.utc)
                       + datetime.timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")
            text = f"Contact: mailto:security@example.org\nExpires: {exp}\nPreferred-Languages: fr, en\n"
            ctype = "text/html" if m == "securitytxt-html" else "text/plain; charset=utf-8"
            return self.body(200, ctype, text.encode())
        if self.path.startswith("/.well-known/") and m != "wellknown-spa":
            return self.body(404, "text/plain", b"")
        return self.body(200, "text/html", b"<html>spa shell</html>")


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
print(srv.server_address[1], flush=True)
srv.serve_forever()
PYSTUB
: > "$WORK/stub.mode"
python3 "$WORK/stub.py" "$WORK/stub.mode" > "$WORK/stub.port" 2>/dev/null &
STUB_PID=$!
for _ in $(seq 1 50); do [ -s "$WORK/stub.port" ] && break; sleep 0.1; done
if [ ! -s "$WORK/stub.port" ]; then
  err "the header stub never reported a port — the edge checks were not exercised"
else
  VISIO_PUBLIC_ORIGIN="http://127.0.0.1:$(cat "$WORK/stub.port")"
  export VISIO_PUBLIC_ORIGIN
  efails() { bash scripts/preflight.sh edge 2>/dev/null | grep -c 'FAIL'; }
  n="$(efails)"
  if [ "$n" -eq 0 ]; then ok "stub in good mode: 0 failures"; else
    err "stub in good mode reported $n failure(s) — the stub or a check is wrong"
    bash scripts/preflight.sh edge 2>/dev/null | grep FAIL
  fi
  # emutate <mode> <fail-text-regex> <label>: the FAIL text is asserted, as
  # in mutate_re, so an unrelated red cannot vouch for a check that never fired.
  emutate() {
    cases=$((cases+1))
    printf '%s\n' "$1" > "$WORK/stub.mode"
    local hit; hit="$(bash scripts/preflight.sh edge 2>/dev/null | grep 'FAIL' | grep -c "$2")"
    if [ "$hit" -ge 1 ]; then ok "detected: $3"; else err "NOT detected: $3"; fi
    : > "$WORK/stub.mode"
  }
  emutate root-no-hsts        'the / redirect ships'      "HSTS missing from the / redirect (the if-block scope bug, as served)"
  emutate api-dup-referrer    'duplicate or conflicting'  "a second, looser Referrer-Policy on /api (the browser takes the last)"
  emutate securitytxt-html    'security.txt answers'      "security.txt served as text/html (the SPA fallback shape)"
  emutate securitytxt-missing 'security.txt answers'      "security.txt absent (404)"
  emutate securitytxt-expired 'security.txt expires'      "security.txt past its Expires date (must not be trusted)"
  emutate wellknown-spa       'well-known/ path answers'  "an unknown /.well-known/ path answered by the SPA shell"
  n="$(efails)"
  if [ "$n" -eq 0 ]; then ok "stub back in good mode: 0 failures"; else err "stub not clean after the last mutation ($n)"; fi
fi

# ── brake: the running gateway's checks, against a stub docker ──────────────
# `preflight.sh stack` reads what nginx loaded (`nginx -T` in the frontend
# container) and what Docker reports of the proxy-tier network. A self-test
# must not need a stack, so the `brake` phase runs those checks alone, here
# against the stub below.
#
# THE STUB IS A MODEL. It answers the two calls the phase makes and refuses
# any other: the fixture's own template rendered the way the nginx entrypoint
# renders it, and a `docker network inspect` document of the shape Docker
# prints. It proves each check can fail and names its cause. It proves nothing
# about a real host — RUNBOOK §5 verifies that from outside.
echo "brake: the running-gateway checks against a stub docker"
mkdir -p "$WORK/bin"
cat > "$WORK/bin/docker" <<'STUB'
#!/usr/bin/env bash
mode="$(cat "$STUB_MODE" 2>/dev/null)"
case "$*" in
  "compose exec -T frontend nginx -T")
    subnet=192.0.2.0/24
    case "$mode" in
      no-gateway)         exit 1 ;;
      trusts-everyone)    subnet=0.0.0.0/0 ;;
      ipv6-of-dual-stack) subnet=2001:db8:1::/64 ;;
      stale-gateway)      subnet=198.51.100.0/24 ;;
    esac
    sed -e "s|\${PROXY_TIER_SUBNET}|$subnet|" "$STUB_TEMPLATE" |
      case "$mode" in
        old-gateway)   sed -e '/limit_req/d' ;;
        trusts-nobody) sed -e '/set_real_ip_from/d' ;;
        *)             cat ;;
      esac ;;
  "network inspect proxy-tier --format {{json .}}")
    net=192.0.2; v6=""
    case "$mode" in other-network|stale-gateway) net=198.51.100 ;; esac
    [ "$mode" = ipv6-of-dual-stack ] && v6=',{"Subnet":"2001:db8:1::/64"}'
    printf '{"Name":"proxy-tier","IPAM":{"Config":[{"Subnet":"%s.0/24"}%s]},"Containers":{"a":{"Name":"nginx-proxy","IPv4Address":"%s.2/24"},"b":{"Name":"visio-frontend-1","IPv4Address":"%s.3/24"}}}\n' \
      "$net" "$v6" "$net" "$net" ;;
  *) echo "stub docker: unmodelled call: $*" >&2; exit 1 ;;
esac
STUB
chmod +x "$WORK/bin/docker"
: > "$WORK/brake.mode"
BRAKE_ENV=(PATH="$WORK/bin:$PATH" STUB_MODE="$WORK/brake.mode" STUB_TEMPLATE="$WORK/nginx/default.conf.template")
clean brake "stub gateway in good mode" "${BRAKE_ENV[@]}"
# bmutate <mode> <FAIL text> <label>: the FAIL text AND a non-zero exit.
bmutate() {
  local out code
  cases=$((cases+1))
  printf '%s\n' "$1" > "$WORK/brake.mode"
  out="$(env "${BRAKE_ENV[@]}" bash scripts/preflight.sh brake 2>/dev/null)"
  code=$?
  if [ "$code" -eq 0 ]; then
    err "NOT detected: $3 — preflight exited 0"
  elif ! printf '%s\n' "$out" | grep 'FAIL' | grep -qF -- "$2"; then
    err "NOT detected: $3 — exited $code, but no FAIL line says: $2"
  else
    ok "detected: $3"
  fi
  : > "$WORK/brake.mode"
}
bmutate old-gateway 'the running gateway lacks the flood brake' \
  "a gateway still running the old template (copied, never recreated)"
bmutate no-gateway "cannot read the running gateway's configuration" \
  "no rendered configuration to read (frontend down)"
bmutate trusts-nobody 'set_real_ip_from lines, expected exactly 1' \
  "a gateway trusting no proxy (every visitor in nginx-proxy's bucket)"
bmutate trusts-everyone "the running gateway trusts X-Forwarded-For from '0.0.0.0/0' (catch-all)" \
  "a gateway trusting every peer"
bmutate other-network "is not the proxy-tier network's" \
  "a valid subnet that belongs to some other network (a recreated proxy-tier, a typo)"
bmutate stale-gateway "but .env holds PROXY_TIER_SUBNET='192.0.2.0/24'" \
  "a gateway trusting a subnet .env no longer holds (never recreated after .env changed)"
bmutate ipv6-of-dual-stack 'proxy-tier containers outside the trusted subnet' \
  "the IPv6 half of a dual-stack proxy-tier, while nginx-proxy connects over IPv4"
clean brake "stub gateway back in good mode" "${BRAKE_ENV[@]}"

# ── Verdict ─────────────────────────────────────────────────────────────────
echo
declared="$(grep -cE '^[[:space:]]*(mutate|mutate_re|mutate_rs|emutate|bmutate) ' "$0")"
if [ "$cases" -ne "$declared" ]; then
  err "ran $cases mutation cases of the $declared this file declares — a section was skipped"
fi
FINISHED=1
if [ "$rc" -eq 0 ]; then echo "preflight self-test passed: every check can still fail ($cases mutation cases)."
else echo "preflight self-test FAILED: a check no longer detects its defect."; fi
exit "$rc"
