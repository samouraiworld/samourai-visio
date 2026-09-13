#!/usr/bin/env bash
# Functional proof of the gateway's flood brake, and of the real client
# address it keys on (deploy/nginx/default.conf.template), run in the nginx
# build the frontend image is made from.
#
# preflight.sh asserts the directives are PRESENT. Presence cannot show that
# the maps match the URLs that mint, that the key is the client rather than
# nginx-proxy, or that the numbers leave a venue alone — and each of those
# fails silently: a map that matches nothing is a brake that never brakes, and
# a key that is nginx-proxy's address is a brake that throttles every visitor
# at once. So this runs the template and counts answers.
#
# There is no backend. A request the brake lets through is proxied to a
# backend that is not there and answers 502; a request it stops answers 429.
# Every case counts both and requires every answer to be one or the other, so
# a gateway that never answered cannot pass as a brake that never tripped.
#
# NOT FOR THE HOST. It creates two throwaway networks on documentation ranges
# (RFC 5737) and three containers, all named after this run, and removes
# exactly those on exit.
#
# Usage:  scripts/check-gateway-brake.sh [template]
#         The template defaults to the repository's; the self-test passes a
#         mutated copy.

set -uo pipefail

tpl="${1:-}"
if [ -n "$tpl" ]; then
  tpl="$(cd "$(dirname "$tpl")" && pwd)/$(basename "$tpl")"
fi
cd "$(git rev-parse --show-toplevel)" || exit 1
TEMPLATE="${tpl:-$PWD/deploy/nginx/default.conf.template}"

# The base of lasuite/meet-frontend:v1.24.0 (src/frontend/Dockerfile at the
# tag), and the image the `nginx -t` step in CI already parses the template with.
IMAGE="${GATEWAY_IMAGE:-nginxinc/nginx-unprivileged:1.30.3-alpine3.23}"

RUN="brake-$$"
GW="$RUN-gw"; PEER="$RUN-proxy"; STRANGER="$RUN-stranger"
TIER="$RUN-tier"; OUTSIDE="$RUN-outside"
TIER_SUBNET=192.0.2.0/24        # plays the proxy tier: PROXY_TIER_SUBNET
OUTSIDE_SUBNET=198.51.100.0/24  # any other peer
URL="http://$GW:8083"
OUT="$(mktemp)"
# Inlined rather than a named function: shellcheck flags an unreachable trap
# body (SC2317/SC2329) differently across versions, and this avoids both.
trap 'docker rm -f "$GW" "$PEER" "$STRANGER" >/dev/null 2>&1; docker network rm "$TIER" "$OUTSIDE" >/dev/null 2>&1; rm -f "$OUT"' EXIT

rc=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; rc=1; }

echo "Gateway flood brake — $(basename "$TEMPLATE") in $IMAGE"
echo

[ -s "$TEMPLATE" ] || { bad "template not found: $TEMPLATE"; exit 1; }

gateway_args=(--add-host backend:127.0.0.1 --add-host frontend:127.0.0.1
              -e BACKEND_INTERNAL_HOST=backend -e FRONTEND_INTERNAL_HOST=frontend
              -v "$TEMPLATE:/etc/nginx/templates/docs.conf.template:ro")

# ── Without the subnet, nginx must refuse rather than trust anyone ─────────
# On the message, not just the exit status: a template with an unrelated
# syntax error also fails `nginx -t`, and would pass this for the wrong reason.
refuses() { # refuses <label> [docker run args...]
  local label="$1"; shift
  local out code
  out="$(docker run --rm "${gateway_args[@]}" "$@" "$IMAGE" nginx -t 2>&1)"
  code=$?
  if [ "$code" -ne 0 ] && printf '%s\n' "$out" | grep -q 'set_real_ip_from'; then
    pass "nginx refuses to start with PROXY_TIER_SUBNET $label"
  else
    bad "nginx did not refuse on set_real_ip_from with PROXY_TIER_SUBNET $label (exit $code)"
    printf '%s\n' "$out" | tail -3 | sed 's/^/        /'
  fi
}
refuses unset
refuses empty -e PROXY_TIER_SUBNET=

# ── The gateway, a peer inside the proxy tier, and one outside it ──────────
if ! docker network create --subnet "$TIER_SUBNET" "$TIER" >/dev/null ||
   ! docker network create --subnet "$OUTSIDE_SUBNET" "$OUTSIDE" >/dev/null; then
  bad "cannot create the two test networks on $TIER_SUBNET and $OUTSIDE_SUBNET"
  exit 1
fi
if ! docker run -d --name "$GW" --network "$TIER" "${gateway_args[@]}" \
       -e PROXY_TIER_SUBNET="$TIER_SUBNET" "$IMAGE" >/dev/null ||
   ! docker network connect "$OUTSIDE" "$GW" ||
   ! docker run -d --name "$PEER" --network "$TIER" --entrypoint sleep "$IMAGE" 900 >/dev/null ||
   ! docker run -d --name "$STRANGER" --network "$OUTSIDE" --entrypoint sleep "$IMAGE" 900 >/dev/null; then
  bad "cannot start the gateway and its two peers"
  exit 1
fi

ready=0
for _ in $(seq 1 40); do
  if [ "$(docker exec "$PEER" curl -s -o /dev/null -w '%{http_code}' "$URL/api/v1.0/config/" 2>/dev/null)" = 502 ]; then
    ready=1
    break
  fi
  sleep 0.5
done
if [ "$ready" -ne 1 ]; then
  bad "the gateway never answered 502 on /api — nginx did not start, or no longer proxies /api"
  docker logs "$GW" 2>&1 | tail -5 | sed 's/^/        /'
  exit 1
fi

# codes <container> <requests> <parallel> <curl args...>
# One status line per request; `{}` in any argument becomes the request's
# sequence number. curl may be handed several URLs: one line per URL.
codes() {
  local c="$1" n="$2" p="$3"
  shift 3
  # shellcheck disable=SC2016  # expanded by the container's shell, not this one
  docker exec "$c" sh -c 'n=$1; p=$2; shift 2; seq "$n" | xargs -P "$p" -I{} "$@"' _ "$n" "$p" \
    curl -s -o /dev/null -w '%{http_code}\n' "$@"
}

tally() { # tally <file>: sets n429 n502 nall nother
  n429="$(grep -cx 429 "$1")"
  n502="$(grep -cx 502 "$1")"
  nall="$(grep -c . "$1")"
  nother=$(( nall - n429 - n502 ))
}

# The two verdicts. <expected> is the number of answers the case must produce.
braked() { # braked <label> <expected> <min admitted>
  tally "$OUT"
  if [ "$nall" -ne "$2" ] || [ "$nother" -ne 0 ]; then
    bad "$1: $nall answers of $2, $nother neither 429 nor 502 — the gateway did not answer the case"
  elif [ "$n429" -lt $(( $2 / 4 )) ]; then
    bad "$1: only $n429 of $2 refused — the brake did not trip"
  elif [ "$n502" -lt "$3" ]; then
    bad "$1: $n502 of $2 admitted, under the burst of $3 the template states — the brake is tighter than documented"
  else
    pass "$1: $n502 admitted, $n429 refused with 429"
  fi
}
free() { # free <label> <expected>
  tally "$OUT"
  if [ "$nall" -ne "$2" ] || [ "$nother" -ne 0 ]; then
    bad "$1: $nall answers of $2, $nother neither 429 nor 502 — the gateway did not answer the case"
  elif [ "$n429" -ne 0 ]; then
    bad "$1: $n429 of $2 refused — the brake throttles traffic it must leave alone"
  else
    pass "$1: all $2 admitted"
  fi
}

xff() { printf 'X-Forwarded-For: %s' "$1"; }
ROOMS="$URL/api/v1.0/rooms"

# ── A burst from one client trips each minting endpoint ────────────────────
# 200 requests at once. The template states burst=100 (room) and burst=60
# (lobby), so at least that many plus one must still be admitted: fewer means
# the request is counted twice somewhere, and a venue would be refused.
codes "$PEER" 200 64 -H "$(xff 203.0.113.10)" "$ROOMS/flood-{}/" > "$OUT"
braked "room: 200-request burst from one client" 200 101

# Straight after, while that client's bucket is still full: the same client is
# still refused, a different client behind the same proxy is not, and the same
# client with a session cookie is not. The second proves the key is the client
# from X-Forwarded-For, not the peer; the third, the cookie's own bucket.
codes "$PEER" 20 20 -H "$(xff 203.0.113.10)" "$ROOMS/again-{}/" > "$OUT"
tally "$OUT"
if [ "$nall" -eq 20 ] && [ "$nother" -eq 0 ] && [ "$n429" -ge 10 ]; then
  pass "room: the same client is still refused right after ($n429 of 20)"
else
  bad "room: the same client right after its burst: $n429 of 20 refused, $nother unexpected — the bucket did not hold"
fi
codes "$PEER" 20 20 -H "$(xff 203.0.113.11)" "$ROOMS/other-{}/" > "$OUT"
free "room: another client behind the same proxy" 20
codes "$PEER" 20 20 -H "$(xff 203.0.113.10)" -H 'Cookie: meet_sessionid=selftest' "$ROOMS/session-{}/" > "$OUT"
free "room: the same client carrying a session cookie" 20

codes "$PEER" 200 64 -H "$(xff 203.0.113.12)" "$ROOMS/suffix-{}.json" > "$OUT"
braked "room: burst on the format suffix (rooms/<slug>.json routes to retrieve)" 200 101
codes "$PEER" 200 64 -I -H "$(xff 203.0.113.13)" "$ROOMS/head-{}/" > "$OUT"
braked "room: burst of HEAD requests (DRF answers HEAD with retrieve)" 200 101

codes "$PEER" 200 64 -X POST -H "$(xff 203.0.113.20)" "$ROOMS/lobby-room/request-entry/" > "$OUT"
braked "lobby: 200-request burst from one client" 200 61

# ── A venue does not trip it ───────────────────────────────────────────────
# One address, the way the SPA joins: GET rooms/<slug> (Django's 301), then
# GET rooms/<slug>/ (the one that mints). A hundred joins at once — the whole
# LT-7 storm (docs/LOAD_TEST.md) from a single address — then a join every
# 0.6 s for 6 s more. curl's -o binds to one URL, hence one per URL.
codes "$PEER" 100 64 -H "$(xff 203.0.113.30)" "$ROOMS/venue-{}" -o /dev/null "$ROOMS/venue-{}/" > "$OUT"
# shellcheck disable=SC2016  # expanded by the container's shell
docker exec "$PEER" sh -c 'for i in $(seq 10); do
    curl -s -w "%{http_code}\n" -H "$1" -o /dev/null "$2/late-$i" -o /dev/null "$2/late-$i/"
    sleep 0.6
  done' _ "$(xff 203.0.113.30)" "$ROOMS" >> "$OUT"
free "room: a venue — 100 joins at once, then one every 0.6 s, each with its redirect hop" 220

# A full room waiting in a lobby behind one address: 30 participants, each
# polling request-entry once a second (useLobby.ts), all started together so
# their polls arrive in the same instant every second — the worst alignment.
# shellcheck disable=SC2016  # expanded by the container's shell
docker exec "$PEER" sh -c 'for p in $(seq 30); do
    ( for t in $(seq 6); do
        curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "$1" "$2"; sleep 1
      done ) &
  done; wait' _ "$(xff 203.0.113.31)" "$ROOMS/lobby-room/request-entry/" > "$OUT"
free "lobby: a full room of 30 polling once a second for 6 s" 180

# ── Trust only the proxy tier ──────────────────────────────────────────────
# A peer outside PROXY_TIER_SUBNET writes a different X-Forwarded-For on every
# request. Ignored, they all land in that peer's own bucket and trip it;
# believed, each would get a fresh bucket and none would.
codes "$STRANGER" 200 64 -H 'X-Forwarded-For: 203.0.113.{}' "$ROOMS/spoof-{}/" > "$OUT"
braked "a peer outside the proxy tier cannot choose its key with X-Forwarded-For" 200 101

# The access log is what an operator reads: the proxy tier's client address
# must be the one logged, and a stranger's claim must not be.
docker exec "$PEER" curl -s -o /dev/null -H "$(xff 203.0.113.77)" "$URL/api/v1.0/config/?probe=$RUN-tier"
docker exec "$STRANGER" curl -s -o /dev/null -H "$(xff 203.0.113.78)" "$URL/api/v1.0/config/?probe=$RUN-outside"
sleep 1
logged_tier="$(docker logs "$GW" 2>/dev/null | grep -F "probe=$RUN-tier" | head -1 | cut -d' ' -f1)"
logged_out="$(docker logs "$GW" 2>/dev/null | grep -F "probe=$RUN-outside" | head -1 | cut -d' ' -f1)"
if [ "$logged_tier" = 203.0.113.77 ]; then
  pass "access log shows the client address the proxy tier reported ($logged_tier)"
else
  bad "access log shows '${logged_tier:-nothing}' for a request the proxy tier made for 203.0.113.77"
fi
case "$logged_out" in
  198.51.100.*) pass "access log shows a stranger's own address ($logged_out), not the one it claimed" ;;
  *) bad "access log shows '${logged_out:-nothing}' for a stranger claiming 203.0.113.78 — expected its own 198.51.100.x" ;;
esac

# ── Everything that does not mint is not counted ───────────────────────────
codes "$PEER" 200 64 -H "$(xff 203.0.113.40)" "$URL/api/v1.0/users/me/" > "$OUT"
free "not counted: the rest of the API (a signed-in user's traffic)" 200
codes "$PEER" 200 64 -X POST -H "$(xff 203.0.113.41)" "$ROOMS/webhooks-livekit/" > "$OUT"
free "not counted: POST actions on the room collection (webhooks, creation callback)" 200
codes "$PEER" 200 64 -X PATCH -H "$(xff 203.0.113.42)" "$ROOMS/some-room/" > "$OUT"
free "not counted: room updates (PATCH on the room itself)" 200
codes "$PEER" 200 64 -H "$(xff 203.0.113.43)" "$ROOMS/some-room/waiting-participants/" > "$OUT"
free "not counted: the room admin's waiting-participants poll" 200

echo
if [ "$rc" -eq 0 ]; then
  echo "The brake trips on floods, leaves venues alone, and keys on the client the proxy tier reports."
else
  echo "GATEWAY BRAKE CHECK FAILED — see the cases above."
fi
exit "$rc"
