#!/usr/bin/env bash
# Deploy preflight for visio.samourai.app.
#
# Every check below exists because the thing it tests fails SILENTLY: a wrong
# env var name is ignored, a JSON list parses into nonsense, a missing mount
# returns 200 text/html, a mismatched LiveKit key yields a healthy stack nobody
# can join. A green `docker compose ps` proves none of it.
#
# DESIGN RULE: a check that cannot fail is worse than no check, because it
# reads as coverage. Every assertion here has been written so that the failure
# mode it describes actually trips it. Where a check can only be advisory, it
# says SKIP and explains what it could not prove — it never reports OK.
#
# Usage:
#   scripts/preflight.sh config    # files on disk; run BEFORE `docker compose up`
#   scripts/preflight.sh stack     # containers running; resolved settings
#   scripts/preflight.sh public    # DNS + TLS; the public surface
#   scripts/preflight.sh all       # all three, in order (default)
#
# Run from the deploy directory on the host (the one holding compose.yaml),
# or set VISIO_DIR. VISIO_ETC overrides /etc for the host-file checks — the
# self-test uses it to point them at a fixture. Never prints a secret.

set -uo pipefail

PHASE="${1:-all}"
DIR="${VISIO_DIR:-$PWD}"
ETC="${VISIO_ETC:-/etc}"
MEET_HOST_DEFAULT="visio.samourai.app"
LIVEKIT_HOST_DEFAULT="livekit.samourai.app"

pass=0; failed=0; skipped=0

ok()   { printf '  \033[32m OK \033[0m  %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; failed=$((failed+1)); }
skip() { printf '  \033[33mSKIP\033[0m  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; skipped=$((skipped+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Read a value from an env file without sourcing it (never executes content).
envval() { grep -m1 "^$2=" "$1" 2>/dev/null | cut -d= -f2- | sed 's/^"//; s/"$//'; }

dc() { docker compose "$@"; }

MEET_HOST="$(envval "$DIR/.env" MEET_HOST)"; MEET_HOST="${MEET_HOST:-$MEET_HOST_DEFAULT}"
LIVEKIT_HOST="$(envval "$DIR/.env" LIVEKIT_HOST)"; LIVEKIT_HOST="${LIVEKIT_HOST:-$LIVEKIT_HOST_DEFAULT}"

# ═══════════════════════════════════════════════════════════════════════════
phase_config() {
  head_ "CONFIG — files on disk (no containers required)"
  cd "$DIR" || { bad "cannot cd to $DIR"; return; }

  # ── Files present ────────────────────────────────────────────────────────
  local missing=""
  for f in .env env.d/common env.d/postgresql livekit-server.yaml compose.yaml compose.override.yaml; do
    [ -f "$f" ] || missing="$missing $f"
  done
  if [ -z "$missing" ]; then ok "all six config files present"
  else bad "missing config files" "$missing"; return; fi

  # ── Unfilled placeholders ────────────────────────────────────────────────
  # Catches <from Clerk dashboard>, <resend api key>, <openssl rand ...>.
  local ph; ph="$(grep -nE '<[^>]+>' .env env.d/common env.d/postgresql livekit-server.yaml 2>/dev/null | grep -v '^\s*#' || true)"
  if [ -z "$ph" ]; then ok "no unfilled <placeholder> in any config file"
  else bad "unfilled placeholders remain" "$(echo "$ph" | cut -d: -f1,2 | tr '\n' ' ')"; fi

  # ── Malformed env lines ──────────────────────────────────────────────────
  # `openssl rand -base64 64` wraps at 64 cols: the second line becomes a junk
  # variable and the secret is truncated, with no error anywhere.
  local mal; mal="$(awk -F= '/^[[:space:]]*#/ {next} /^[[:space:]]*$/ {next} NF<2 || $1 ~ /[^A-Z0-9_]/ {print NR}' env.d/common 2>/dev/null | tr '\n' ' ')"
  if [ -z "$mal" ]; then ok "every line in env.d/common is a well-formed KEY=value"
  else bad "malformed lines in env.d/common (a wrapped secret looks exactly like this)" "line(s): $mal"; fi

  # ── JSON-shaped lists ────────────────────────────────────────────────────
  # values.ListValue splits on ',' and never parses JSON.
  local js; js="$(grep -nE '^[A-Z][A-Z0-9_]*=\[' env.d/common 2>/dev/null | cut -d: -f1 | tr '\n' ' ')"
  if [ -z "$js" ]; then ok "no JSON-shaped list values (ListValue splits on ',')"
  else bad "bracketed list value(s) — these parse into nonsense silently" "line(s): $js"; fi

  # ── LiveKit shared secret ────────────────────────────────────────────────
  # A mismatch is invisible: healthy stack, TLS fine, and every token fails
  # signature validation so nobody can join any room.
  local a b
  a="$(grep -E '^[[:space:]]+meet:' livekit-server.yaml 2>/dev/null | sed 's/.*meet:[[:space:]]*//' | tr -d '"'"'"' ')"
  b="$(envval env.d/common LIVEKIT_API_SECRET)"
  if [ -z "$a" ] || [ -z "$b" ]; then bad "LiveKit secret missing on one side" "livekit-server.yaml keys.meet, or LIVEKIT_API_SECRET"
  elif [ "$a" = "$b" ]; then ok "LiveKit secret matches across livekit-server.yaml and env.d/common"
  else bad "LiveKit secret MISMATCH — the stack will look healthy and nobody will be able to join"; fi

  # ── Keycloak leftovers ───────────────────────────────────────────────────
  local kc; kc="$(grep -nE '^(OIDC_OP_LOGOUT_ENDPOINT|KEYCLOAK_HOST|REALM_NAME)=' env.d/common .env 2>/dev/null || true)"
  if [ -z "$kc" ]; then ok "no Keycloak leftovers; OIDC_OP_LOGOUT_ENDPOINT correctly unset"
  else bad "upstream Keycloak config survived the copy" "$(echo "$kc" | cut -d: -f1,2 | tr '\n' ' ')"; fi

  # ── The CSS variable that does not exist ─────────────────────────────────
  if grep -q '^FRONTEND_CUSTOM_CSS_URL=' env.d/common 2>/dev/null; then
    if grep -qE '^FRONTEND_CSS_URL=' env.d/common; then bad "FRONTEND_CSS_URL is set — it is not a Meet setting and is ignored silently"
    else ok "FRONTEND_CUSTOM_CSS_URL set (and the non-existent FRONTEND_CSS_URL is not)"; fi
  else bad "FRONTEND_CUSTOM_CSS_URL is not set — the theme will never load"; fi

  # ── Branding assets exist ────────────────────────────────────────────────
  # Docker silently creates a DIRECTORY when a bind-mount source is missing.
  local ba=""
  [ -s custom/style.css ] || ba="$ba custom/style.css"
  [ -s custom/logo.png ]  || ba="$ba custom/logo.png"
  if [ -z "$ba" ]; then ok "branding assets present and non-empty"
  else bad "missing branding assets (Docker will mount a directory in their place)" "$ba"; fi

  # ── Landing page: the setting and the files must agree ───────────────────
  # Both halves fail silently on their own. A set URL with no files behind it
  # bounces every anonymous visitor onto the SPA fallback (200 text/html), and
  # files with no URL set are simply never reached.
  local ehu; ehu=$(envval env.d/common FRONTEND_EXTERNAL_HOME_URL)
  if [ -n "$ehu" ]; then
    if [ -s landing/index.html ]; then
      ok "landing page present and FRONTEND_EXTERNAL_HOME_URL set"
    else
      bad "FRONTEND_EXTERNAL_HOME_URL is set but landing/index.html is missing or empty" \
          "anonymous visitors would be redirected to the SPA fallback, which looks like a redirect loop"
    fi
    case "$ehu" in
      */) : ;;
      *) bad "FRONTEND_EXTERNAL_HOME_URL has no trailing slash" \
             "nginx answers /accueil with a 301 to /accueil/ — redirect the visitor once, not twice" ;;
    esac
  elif [ -s landing/index.html ]; then
    bad "landing/index.html exists but FRONTEND_EXTERNAL_HOME_URL is unset" \
        "the page is served but nothing ever sends visitors to it"
  else
    skip "no landing page configured" "upstream's own home page will be served to anonymous visitors"
  fi

  # ── Interface language ───────────────────────────────────────────────────
  # Upstream defaults to en-us and never warns. Only four values are wired
  # (settings.py:227-234); anything else falls back silently to English.
  local lang; lang=$(envval env.d/common DJANGO_LANGUAGE_CODE)
  case "$lang" in
    fr-fr|en-us|nl-nl|de-de) ok "DJANGO_LANGUAGE_CODE=$lang is a supported locale" ;;
    "") bad "DJANGO_LANGUAGE_CODE is unset — the backend default locale stays en-us (upstream default)" \
            "sets the default User.language and the last-resort e-mail fallback; it does NOT set the SPA's interface language" ;;
    *)  bad "DJANGO_LANGUAGE_CODE=$lang is not one of en-us, fr-fr, nl-nl, de-de" \
            "unsupported values fall back to English with no error" ;;
  esac

  # ── TURN config traps ────────────────────────────────────────────────────
  if grep -qE '^[[:space:]]*enabled:[[:space:]]*true' livekit-server.yaml 2>/dev/null; then
    if grep -qE '^[[:space:]]*tls_port:[[:space:]]*0' livekit-server.yaml; then
      ok "TURN enabled with tls_port: 0 (any value > 0 demands a cert and refuses to start)"
    else
      bad "TURN enabled without tls_port: 0" "LiveKit defaults it to 5349, loads cert_file/key_file, and exits"
    fi
    local rs re
    rs="$(grep -E '^[[:space:]]*relay_range_start:' livekit-server.yaml | grep -oE '[0-9]+' || true)"
    re="$(grep -E '^[[:space:]]*relay_range_end:' livekit-server.yaml | grep -oE '[0-9]+' || true)"
    if [ -n "$rs" ] && [ -n "$re" ] && grep -q "$rs-$re:$rs-$re/udp" compose.override.yaml 2>/dev/null; then
      ok "TURN relay range $rs-$re is published in compose"
    else
      bad "TURN relay range is not published, or does not match compose" "livekit says ${rs:-unset}-${re:-unset}; allocations on unpublished ports are unreachable"
    fi
  else
    skip "TURN not enabled" "restrictive-network users will get signalling but no media"
  fi

  # ── Compose merge + pinning ──────────────────────────────────────────────
  # --no-env-resolution: leaves env_file unexpanded so no secret is printed.
  if ! dc config --no-env-resolution -q >/dev/null 2>&1; then
    bad "compose config is invalid"; return
  fi
  ok "compose.yaml + compose.override.yaml merge into a valid config"

  # `grep -c latest` is NOT sufficient: an untagged image renders with no tag
  # at all, is implicitly :latest, and contains no "latest" to match.
  local float=""
  while read -r img; do
    case "$img" in
      *:latest|*:main|*:master|*:edge) float="$float $img" ;;
      *:*) ;;
      *) float="$float $img(untagged)" ;;
    esac
  done < <(dc config --images 2>/dev/null)
  if [ -z "$float" ]; then ok "every image is pinned to a fixed tag"
  else bad "floating image tag(s) — an upstream push will restart production unannounced" "$float"; fi

  dc config --no-env-resolution --format json > /tmp/preflight-cfg.json 2>/dev/null
  local merge; merge="$(python3 - <<'PY'
import json
try:
    svc = json.load(open("/tmp/preflight-cfg.json"))["services"]
except Exception as e:
    print(f"cannot parse compose config: {e}"); raise SystemExit
bad = []
tg = {v.get("target") for v in svc.get("frontend", {}).get("volumes", [])}
for want in ("/etc/nginx/templates/docs.conf.template", "/usr/share/nginx/html/custom",
             "/usr/share/nginx/html/accueil"):
    if want not in tg:
        bad.append(f"frontend missing mount {want}")
for n in ("postgresql", "redis", "backend", "frontend", "livekit"):
    if not svc.get(n, {}).get("restart"):
        bad.append(f"{n} has no restart policy (will not survive a reboot)")
    if svc.get(n, {}).get("logging", {}).get("driver") != "journald":
        bad.append(f"{n} does not log to journald (the 7-day retention never applies to it)")
if "/data" not in {v.get("target") for v in svc.get("redis", {}).get("volumes", [])}:
    bad.append("redis has no /data volume (every restart logs out every user)")
print("; ".join(bad))
PY
)"
  if [ -z "$merge" ]; then ok "override merges with upstream: all three frontend mounts, restart policies, journald logging, redis volume"
  else bad "compose merge problems" "$merge"; fi

  # ── Permissions ──────────────────────────────────────────────────────────
  local perm=""
  for f in .env env.d/common env.d/postgresql; do
    local m; m="$(stat -c '%a' "$f" 2>/dev/null || stat -f '%Lp' "$f" 2>/dev/null)"
    [ "$m" = "600" ] || perm="$perm $f($m)"
  done
  if [ -z "$perm" ]; then ok "secret files are mode 600"
  else bad "secret files are world- or group-readable" "$perm"; fi

  # ── Log retention (the privacy policy's 7-day promise) ───────────────────
  # landing/confidentialite/ states IP-bearing logs are deleted after 7 days.
  # json-file cannot do age-based retention, so everything logs to journald
  # and journald enforces the clock. Three pieces, each silent when missing:
  # the compose logging driver (asserted in the merge block above), the
  # journald drop-in, and the daemon default for containers outside this
  # compose project — nginx-proxy, which logs every client IP.
  if [ -d "$ETC/systemd" ]; then
    local jr="$ETC/systemd/journald.conf.d/visio-retention.conf"
    if [ ! -f "$jr" ]; then
      bad "journald retention drop-in missing: $jr" \
          "install per RUNBOOK §8bis, or the published 7-day log retention is not enforced"
    else
      local ret maxf stor
      ret="$(grep -m1 '^MaxRetentionSec=' "$jr" | cut -d= -f2)"
      maxf="$(grep -m1 '^MaxFileSec=' "$jr" | cut -d= -f2)"
      stor="$(grep -m1 '^Storage=' "$jr" | cut -d= -f2)"
      if [ "$ret" = "7day" ] && [ "$maxf" = "1day" ] && [ "$stor" = "persistent" ]; then
        ok "journald drop-in enforces the 7-day retention the privacy policy promises"
      else
        bad "journald drop-in drifted (MaxRetentionSec=${ret:-unset} MaxFileSec=${maxf:-unset} Storage=${stor:-unset})" \
            "expected 7day / 1day / persistent — the published retention and the enforced one must match"
      fi
    fi

    local dj="$ETC/docker/daemon.json"
    local drv
    drv="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("log-driver",""))' "$dj" 2>/dev/null)"
    if [ "$drv" = "journald" ]; then
      ok "docker default log driver is journald (covers nginx-proxy and any future container)"
    else
      bad "docker default log driver is '${drv:-unreadable}', not journald ($dj)" \
          "containers outside this compose project keep unbounded json-file logs — nginx-proxy logs every client IP"
    fi

    local lr="$ETC/logrotate.d/rsyslog"
    if [ -f "$lr" ]; then
      local slow; slow="$(grep -nE 'weekly|rotate 4' "$lr" || true)"
      if [ -z "$slow" ]; then
        ok "rsyslog file copies rotate daily and keep 7 (auth.log, kern.log)"
      else
        bad "rsyslog logrotate keeps file copies beyond 7 days" \
            "$(echo "$slow" | tr '\n' ' ') — tighten per RUNBOOK §8bis"
      fi
    else
      skip "no $lr" "no rsyslog file copies to rotate; journald retention covers the journal itself"
    fi
  else
    skip "not a systemd host ($ETC/systemd missing)" \
         "log retention cannot be asserted here — on the deploy host this must never skip"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
phase_stack() {
  head_ "STACK — running containers and resolved settings"
  cd "$DIR" || { bad "cannot cd to $DIR"; return; }

  local up; up="$(dc ps --services --filter status=running 2>/dev/null | tr '\n' ' ')"
  if [ -z "$up" ]; then bad "no services running" "run 'docker compose up -d' first"; return; fi

  local down=""
  for s in postgresql redis backend frontend livekit; do
    echo "$up" | grep -qw "$s" || down="$down $s"
  done
  if [ -z "$down" ]; then ok "all five services running"
  else bad "services not running" "$down"; fi

  if dc ps backend 2>/dev/null | grep -q "healthy"; then ok "backend reports healthy"
  else bad "backend is not healthy" "docker compose logs backend — usual causes: an unfilled placeholder, or a wrapped secret"; fi

  # ── Interpolation actually resolved ──────────────────────────────────────
  # Undefined variables render as the EMPTY STRING with a warning, not as a
  # literal ${VAR} — so grepping for '${' can never catch this. Assert the
  # values are non-empty and well-formed instead.
  local envout; envout="$(dc exec -T backend printenv DJANGO_ALLOWED_HOSTS MEET_BASE_URL LIVEKIT_API_URL OIDC_OP_TOKEN_ENDPOINT 2>/dev/null)"
  local n; n="$(echo "$envout" | grep -c .)"
  if [ "$n" -ne 4 ]; then
    bad "one or more critical env vars are EMPTY in the container" "expected 4 non-empty values, got $n — interpolation did not resolve"
  elif printf '%s' "$envout" | grep -qF "$(printf '$''{')"; then  # literal ${ — interpolation never ran
    bad "literal \${VAR} reached the container — interpolation did not run"
  elif echo "$envout" | grep -qE 'https?:///|//$'; then
    bad "a malformed URL reached the container" "an empty variable collapsed a URL, e.g. https:///realms//..."
  else
    ok "env interpolation resolved: hosts and endpoints are non-empty and well-formed"
  fi

  # ── Resolved Django settings genuinely parse ─────────────────────────────
  # This is the check that catches the JSON-list bug at the only layer that
  # matters: what Django ended up with. None of these are secrets.
  local s; s="$(dc exec -T backend python manage.py shell -c "
from django.conf import settings as s
import json
print(json.dumps({
 'fullname': s.OIDC_USERINFO_FULLNAME_FIELDS,
 'allowed_redirect': s.OIDC_REDIRECT_ALLOWED_HOSTS,
 'essential': list(s.OIDC_USERINFO_ESSENTIAL_CLAIMS),
 'allowed_hosts': s.ALLOWED_HOSTS,
 'scopes': s.OIDC_RP_SCOPES,
 'proxy': list(s.SECURE_PROXY_SSL_HEADER or []),
 'ssl_redirect': s.SECURE_SSL_REDIRECT,
 'unregistered': s.ALLOW_UNREGISTERED_ROOMS,
 'logout': bool(s.OIDC_OP_LOGOUT_ENDPOINT),
}))" 2>/dev/null | tr -d '\r' | grep '^{')"

  if [ -z "$s" ]; then
    bad "could not read resolved Django settings" "docker compose logs backend"
  else
    local verdict; verdict="$(python3 - "$s" <<'PY'
import json, sys
d = json.loads(sys.argv[1]); bad = []
for k in ("fullname", "allowed_redirect", "essential", "allowed_hosts"):
    for item in d[k]:
        if any(c in item for c in '["]'):
            bad.append(f"{k}={d[k]!r} contains bracket/quote — the JSON form did NOT parse")
            break
if not d["fullname"]:
    bad.append("OIDC_USERINFO_FULLNAME_FIELDS is empty — every display name will be blank")
if "profile" not in d["scopes"]:
    bad.append(f"OIDC_RP_SCOPES={d['scopes']!r} lacks 'profile' — no name claims will arrive")
if d["proxy"] != ["HTTP_X_FORWARDED_PROTO", "https"]:
    bad.append(f"SECURE_PROXY_SSL_HEADER={d['proxy']!r} is not the expected pair")
if not d["unregistered"]:
    bad.append("ALLOW_UNREGISTERED_ROOMS is False — guests cannot create ad-hoc rooms")
if d["logout"]:
    bad.append("OIDC_OP_LOGOUT_ENDPOINT is set — Clerk advertises none; logout will break")
print("; ".join(bad))
PY
)"
    if [ -z "$verdict" ]; then ok "resolved Django settings parse correctly (lists are real lists, scopes include profile)"
    else bad "resolved settings are wrong" "$verdict"; fi
  fi

  # ── Redis persistence ────────────────────────────────────────────────────
  local aof; aof="$(dc exec -T redis redis-cli CONFIG GET appendonly 2>/dev/null | tr -d '\r' | tail -1)"
  if [ "$aof" = "yes" ]; then ok "redis AOF persistence on (sessions survive a restart)"
  else bad "redis appendonly=${aof:-unknown} — every restart logs out every user mid-call"; fi

  # ── Migrations ───────────────────────────────────────────────────────────
  local unap; unap="$(dc exec -T backend python manage.py showmigrations --plan 2>/dev/null | grep -c '^\[ \]' || echo 0)"
  if [ "$unap" = "0" ]; then ok "no unapplied migrations"
  else bad "$unap unapplied migration(s)" "run: docker compose run --rm backend python manage.py migrate"; fi

  # ── Log retention, runtime half ──────────────────────────────────────────
  # The config phase proves the FILES; this proves the runtime picked them up.
  # A container keeps the log driver it was CREATED with — neither `restart`
  # nor a daemon.json edit changes it. Only recreation does. This inspects
  # every running container on the box, so it catches nginx-proxy too, which
  # lives in another compose project.
  local nonj=""
  while read -r cname; do
    local cdrv
    cdrv="$(docker inspect -f '{{.HostConfig.LogConfig.Type}}' "$cname" 2>/dev/null)"
    [ "$cdrv" = "journald" ] || nonj="$nonj $cname(${cdrv:-unknown})"
  done < <(docker ps --format '{{.Names}}')
  if [ -z "$nonj" ]; then ok "every running container logs to journald (nginx-proxy included)"
  else bad "container(s) on another log driver — the 7-day clock does not apply to them" \
           "$nonj — recreate them (up -d / --force-recreate), a restart is not enough"; fi

  # The public promise is "7 days, then deletion", and rotation is daily, so
  # no surviving entry may be older than 8 days. This is the only check that
  # proves deletion actually HAPPENS — the drop-in existing proves intent.
  # `head -1` closes the pipe after one line, so this never streams the
  # journal. A journal younger than the window passes trivially, which is
  # correct: the invariant holds.
  local oldest
  oldest="$(journalctl -q -o short-unix 2>/dev/null | head -1 | cut -d' ' -f1 | cut -d. -f1)"
  if [ -z "$oldest" ]; then
    skip "cannot read the journal (journalctl missing, or empty journal)" \
         "the 7-day deletion is unproven on this host"
  else
    local age; age=$(( ($(date +%s) - oldest) / 86400 ))
    if [ "$age" -le 8 ]; then
      ok "oldest journal entry is ${age} day(s) old — inside the published 7-day window"
    else
      bad "oldest journal entry is ${age} days old — retention is configured but not deleting" \
          "restart systemd-journald after installing the drop-in, then journalctl --vacuum-time=7d"
    fi
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
phase_public() {
  head_ "PUBLIC — DNS, TLS and the live surface"

  # ── DNS ──────────────────────────────────────────────────────────────────
  local a1 a2
  a1="$(dig +short "$MEET_HOST" A | tail -1)"
  a2="$(dig +short "$LIVEKIT_HOST" A | tail -1)"
  if [ -n "$a1" ] && [ "$a1" = "$a2" ]; then ok "$MEET_HOST and $LIVEKIT_HOST resolve to the same address"
  else bad "DNS mismatch or missing" "$MEET_HOST=${a1:-none} $LIVEKIT_HOST=${a2:-none}"; fi

  local aaaa; aaaa="$(dig +short "$MEET_HOST" AAAA)"
  if [ -z "$aaaa" ]; then ok "no stray AAAA record (Let's Encrypt would validate over IPv6 and fail)"
  else skip "AAAA record present" "$aaaa — ensure the host actually serves on IPv6, or issuance will fail"; fi

  # ── TLS ──────────────────────────────────────────────────────────────────
  for h in "$MEET_HOST" "$LIVEKIT_HOST"; do
    local c; c="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://$h/" 2>/dev/null)"
    if [ -n "$c" ] && [ "$c" != "000" ]; then ok "https://$h serves (HTTP $c), certificate valid"
    else bad "https://$h did not serve over TLS"; fi
  done

  # ── Redirect loop, on a URL that actually reaches Django ─────────────────
  # `/` is served by the frontend SPA. SECURE_SSL_REDIRECT is Django
  # middleware, so a loop can only appear on /api or /admin.
  for p in /api/v1.0/config/ /admin/; do
    local out; out="$(curl -sS -o /dev/null -w '%{num_redirects} %{url_effective}' -L --max-time 20 "https://${MEET_HOST}${p}" 2>/dev/null)"
    local nr="${out%% *}" fin="${out#* }"
    if [ "${nr:-99}" -le 2 ] && [ "${fin#http://}" = "$fin" ]; then ok "$p terminates in $nr redirect(s), stays on https"
    else bad "$p redirect problem" "$nr redirects, ended at $fin — X-Forwarded-Proto is probably not arriving"; fi
  done

  # ── Scheme spoofing ──────────────────────────────────────────────────────
  # nginx-proxy forwards a client-supplied X-Forwarded-Proto unless
  # TRUST_DOWNSTREAM_PROXY=false. Django trusts that header.
  local sp; sp="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -H 'X-Forwarded-Proto: https' "http://${MEET_HOST}/" 2>/dev/null)"
  case "$sp" in
    30*) ok "a spoofed X-Forwarded-Proto is ignored (HTTP $sp to https)" ;;
    200) bad "SCHEME SPOOFING: a client-supplied X-Forwarded-Proto is trusted" "set TRUST_DOWNSTREAM_PROXY=false on nginx-proxy" ;;
    *)   skip "spoof test inconclusive (HTTP ${sp:-none})" "port 80 may be closed to this client" ;;
  esac

  # ── Theme actually served ────────────────────────────────────────────────
  # The SPA fallback (`error_page 404 =200 /index.html`) means a MISSING file
  # returns 200 text/html, never 404. Asserting on status can never catch it.
  local ct; ct="$(curl -sS -o /dev/null -w '%{content_type}' --max-time 15 "https://${MEET_HOST}/custom/style.css" 2>/dev/null)"
  case "$ct" in
    text/css*) ok "/custom/style.css served as text/css" ;;
    text/html*) bad "/custom/style.css returns text/html — the bind-mount is MISSING" "the SPA fallback returns 200 for missing files; the browser will refuse the stylesheet" ;;
    *) bad "/custom/style.css unexpected content-type: ${ct:-none}" ;;
  esac

  local li; li="$(curl -sS -o /dev/null -w '%{content_type}' --max-time 15 "https://${MEET_HOST}/custom/logo.png" 2>/dev/null)"
  case "$li" in
    image/*) ok "/custom/logo.png served as ${li} (invitation emails will render it)" ;;
    *) bad "/custom/logo.png is ${li:-missing} — every invitation email ships a broken image" ;;
  esac

  # ── Backend advertises the CSS ───────────────────────────────────────────
  local cfg; cfg="$(curl -sS --max-time 15 "https://${MEET_HOST}/api/v1.0/config/" 2>/dev/null)"
  if echo "$cfg" | grep -q '"custom_css_url"[[:space:]]*:[[:space:]]*"[^"]'; then
    ok "backend advertises custom_css_url to the frontend"
  else
    bad "custom_css_url is absent or null in /api/v1.0/config/" "FRONTEND_CUSTOM_CSS_URL is unset, misspelled, or the backend was not restarted"
  fi

  # ── Landing page: advertised AND actually served ─────────────────────────
  # Two independent failures. The backend can advertise a URL that serves the
  # SPA fallback, which sends every anonymous visitor back into the app — it
  # reads as a redirect loop and would be debugged as an auth problem.
  local ehu; ehu="$(echo "$cfg" | sed -n 's/.*"external_home_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  if [ -n "$ehu" ]; then
    ok "backend advertises external_home_url ($ehu)"
    # Content, not status: a missing mount also returns 200 text/html.
    local body; body="$(curl -sSL --max-time 15 "$ehu" 2>/dev/null)"
    if echo "$body" | grep -q 'id="start-btn"'; then
      ok "landing page is really served at $ehu"
    else
      bad "external_home_url does not serve the landing page" \
          "the ./landing bind-mount is missing — the SPA fallback answers 200 text/html, so anonymous visitors bounce straight back into the app"
    fi

    # ── Legal pages, content-asserted ────────────────────────────────────────
    # Same SPA-fallback trap: a missing file answers 200 text/html, so the
    # status code proves nothing. Assert on our own SIREN, which upstream's
    # DINUM pages could never contain — that distinguishes "our page is served"
    # from "the app answered something".
    local base; base="${ehu%/}"
    local ml; ml="$(curl -sSL --max-time 15 "${base}/mentions-legales/" 2>/dev/null)"
    if echo "$ml" | grep -q "830 485 108"; then
      ok "our mentions légales are served (LCEN art. 6-III)"
    else
      bad "mentions légales are not served at ${base}/mentions-legales/" \
          "without them the footer link is dead, and the only legal pages reachable on this host are upstream's, which name DINUM as publisher"
    fi
    local pc; pc="$(curl -sSL --max-time 15 "${base}/confidentialite/" 2>/dev/null)"
    if echo "$pc" | grep -q "responsable du traitement"; then
      ok "our privacy policy is served (GDPR art. 13)"
    else
      bad "privacy policy is not served at ${base}/confidentialite/"
    fi

    # ── The no-third-party claim, verified where it is made ──────────────────
    # The landing and the privacy policy both state that nothing is loaded from
    # a third party. Assert it against what production actually serves, not
    # against the repo — the deployed theme is a copy an operator may edit.
    local css; css="$(curl -sS --max-time 15 "https://${MEET_HOST}/custom/style.css" 2>/dev/null)"
    if printf '%s' "$css" | grep -qE '@import[^;]*https?://|url\(["'"'"']?https?://'; then
      bad "the deployed theme loads a third-party resource" \
          "every visitor's IP and User-Agent leak to it, on every page including inside rooms — and the privacy policy states the opposite"
    else
      ok "the deployed theme loads nothing from a third party"
    fi
  else
    skip "no external_home_url advertised" "anonymous visitors get upstream's home page, not ours"
  fi

  # ── Backend default locale ───────────────────────────────────────────────
  # This proves the BACKEND locale only. It does NOT prove the interface
  # language: the SPA picks its own via i18next browser detection
  # (order: localStorage, navigator — fallbackLng 'fr'), and LANGUAGE_CODE
  # appears in none of the JS chunks it serves. Invitation e-mails follow the
  # SENDER's Accept-Language through LocaleMiddleware, with this value as the
  # last-resort fallback. Labelling this "interface language" would be a check
  # reporting coverage it does not have.
  local lc; lc="$(echo "$cfg" | sed -n 's/.*"LANGUAGE_CODE"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  case "$lc" in
    fr-fr) ok "backend default locale is fr-fr (proves the container was recreated, not merely restarted)" ;;
    "")    skip "LANGUAGE_CODE absent from /api/v1.0/config/" ;;
    *)     bad "backend default locale is $lc, not fr-fr" "DJANGO_LANGUAGE_CODE unset, or the backend was restarted instead of recreated (restart does not reload env)" ;;
  esac
  skip "interface language cannot be asserted from the server" \
       "the SPA resolves it client-side from the visitor's browser; check it in a browser with a French locale"

  # ── Guest path: the ONLY test that exercises ALLOW_UNREGISTERED_ROOMS ─────
  # It fires only on Http404 — a slug NOT in the database. A room created by a
  # logged-in user never reaches it.
  local slug; slug="preflight-$(date +%s)-$$"
  local body; body="$(curl -sS --max-time 20 "https://${MEET_HOST}/api/v1.0/rooms/${slug}?username=preflight" 2>/dev/null)"
  if echo "$body" | grep -q '"livekit"' && echo "$body" | grep -q '"slug"'; then
    ok "guest path works: an unknown slug materialises a room with a LiveKit token"
  else
    bad "ALLOW_UNREGISTERED_ROOMS is not working for anonymous visitors" "GET /api/v1.0/rooms/<never-created-slug> did not return a room+token"
  fi

  # ── Clerk still matches what the config assumes ──────────────────────────
  local disc; disc="$(curl -sS --max-time 15 https://clerk.samourai.app/.well-known/openid-configuration 2>/dev/null)"
  local tok; tok="$(envval "$DIR/env.d/common" OIDC_OP_TOKEN_ENDPOINT)"
  if [ -n "$disc" ] && [ -n "$tok" ] && echo "$disc" | grep -qF "$tok"; then
    ok "Clerk discovery still advertises the configured token endpoint"
  elif [ -z "$disc" ]; then bad "Clerk discovery document unreachable"
  else bad "configured OIDC endpoint no longer matches Clerk discovery" "re-derive env.d/common from the live document"; fi

  # ── Things this script structurally cannot prove ─────────────────────────
  skip "UDP reachability (7882, 443, relay range)" "'nc -zu' reports success against a DROPping firewall; and run from the host it tests loopback. Prove it with a real call and read LiveKit's selected ICE candidate pair."
  skip "Scaleway security group" "a second filter ufw cannot see. Check it in the console."
  skip "silent login (prompt=none) for a first-time anonymous visitor" "needs a real browser with no session; the callback only handles error=login_required gracefully."
}

# ═══════════════════════════════════════════════════════════════════════════
printf '\033[1mvisio preflight\033[0m — %s  (dir: %s)\n' "$PHASE" "$DIR"

case "$PHASE" in
  config) phase_config ;;
  stack)  phase_stack ;;
  public) phase_public ;;
  all)    phase_config; phase_stack; phase_public ;;
  *)      echo "usage: $0 [config|stack|public|all]"; exit 2 ;;
esac

printf '\n\033[1m%d passed, %d failed, %d skipped\033[0m\n' "$pass" "$failed" "$skipped"
[ "$skipped" -gt 0 ] && echo "SKIP means unproven, not fine — read each one."
if [ "$failed" -gt 0 ]; then
  echo "Do not proceed until the failures above are resolved."
  exit 1
fi
echo "No failures. Note the skips: they are the checks a script cannot make."
