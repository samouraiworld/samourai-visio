#!/usr/bin/env bash
# Nightly PostgreSQL backup for visio.samourai.app — dump, verify, ship
# off-box, verify the remote copy, prune, and only then touch the freshness
# marker.
#
# Design rules, same as preflight.sh:
#   * assert on OUTPUT (dump header, byte sizes), never on incidental exit
#     codes alone;
#   * every failure prints FAIL and exits non-zero — the cron line pipes
#     stdout to logger, and `preflight.sh stack` asserts the marker's
#     freshness, so a silently failing backup turns a check red within a day;
#   * ~/backups/LAST_OK is written only after the remote copy is verified by
#     size. A local-only dump is not a backup: "off-box" is the requirement,
#     and the marker must never say otherwise.
#
# The remote keeps BACKUP_KEEP_REMOTE_DAYS days of dumps — the number the
# privacy policy publishes, so the prune is not housekeeping, it is the
# enforcement of a published retention period and is asserted as an invariant
# (oldest surviving object), never as "the delete command exited 0".
# Restore drill: RUNBOOK §8ter. An untested backup is not a backup.
#
# Usage: run from ~/visio, or set VISIO_DIR. Needs docker compose, rclone,
# and env.d/backup (template: deploy/env.d/backup.example).

set -uo pipefail
# The dump and the marker carry every user's email and room metadata. cron's
# default umask is 022, which would leave them 0644 — world-readable PII for
# as long as the local copies live.
umask 077
DIR="${VISIO_DIR:-$PWD}"
cd "$DIR" || { echo "FAIL cannot cd to $DIR"; exit 1; }

fail() { echo "FAIL $1"; exit 1; }
# Read a value from an env file without sourcing it (never executes content).
envval() { grep -m1 "^$2=" "$1" 2>/dev/null | cut -d= -f2- | sed 's/^"//; s/"$//'; }

[ -f env.d/backup ] || fail "env.d/backup missing (template: deploy/env.d/backup.example)"
command -v rclone >/dev/null 2>&1 || fail "rclone not installed (apt-get install rclone)"

# Export the rclone remote definition without sourcing the file. Only
# RCLONE_CONFIG_VISIO_* keys are exported, nothing else is evaluated.
# shellcheck disable=SC2163  # dynamic export; the key is validated by grep + case
while IFS='=' read -r k v; do
  case "$k" in
    RCLONE_CONFIG_VISIO_*) export "$k=$v" ;;
  esac
done < <(grep -E '^RCLONE_CONFIG_VISIO_[A-Z0-9_]+=' env.d/backup)

REMOTE="$(envval env.d/backup BACKUP_REMOTE_PATH)"
KEEP_LOCAL="$(envval env.d/backup BACKUP_KEEP_LOCAL_DAYS)"; KEEP_LOCAL="${KEEP_LOCAL:-7}"
KEEP_REMOTE="$(envval env.d/backup BACKUP_KEEP_REMOTE_DAYS)"; KEEP_REMOTE="${KEEP_REMOTE:-30}"
[ -n "$REMOTE" ] || fail "BACKUP_REMOTE_PATH unset in env.d/backup"
case "$REMOTE" in
  *"<"*) fail "env.d/backup still carries a <placeholder>" ;;
  *:*) : ;;
  *) fail "BACKUP_REMOTE_PATH is not remote:bucket/prefix ($REMOTE)" ;;
esac

DB_USER="$(envval env.d/postgresql DB_USER)"; DB_USER="${DB_USER:-meet}"
DB_NAME="$(envval env.d/postgresql DB_NAME)"; DB_NAME="${DB_NAME:-meet}"

OUTDIR="$HOME/backups"
mkdir -p "$OUTDIR"
chmod 700 "$OUTDIR"
OUT="$OUTDIR/visio-$(date +%F-%H%M).sql.gz"

docker compose exec -T postgresql pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$OUT" \
  || fail "pg_dump exited non-zero"

# The dump must gunzip cleanly, start like a pg_dump, and have plausible mass.
gunzip -t "$OUT" 2>/dev/null || fail "not a valid gzip: $OUT"
# Read the header into a variable FIRST. Piping gunzip into `head` closes the
# pipe early, gunzip dies of SIGPIPE, and `set -o pipefail` surfaces 141 — so
# the obvious `gunzip -c | head -3 | grep -q` form fails on every dump larger
# than the ~64 KiB pipe buffer while passing on tiny fixtures. Verified:
# 4 KB dump exit 0, 363 KB dump exit 141. A command substitution ignores the
# producer's signal status, and this also honours the repo rule — assert on
# output, never on a pipeline's exit code.
hdr="$(gunzip -c "$OUT" 2>/dev/null | head -c 4096)"
printf '%s' "$hdr" | grep -q "PostgreSQL database dump" \
  || fail "dump lacks the pg_dump header: $OUT"
size="$(wc -c < "$OUT" | tr -d ' ')"
# 4096, not 10240: on a young instance a real dump (schema + a handful of
# users/rooms) compresses to ~8 KB. Verified against a live dump containing
# 3 real users and 8 real rooms (8121 bytes) — 10240 was rejecting genuine
# backups outright, silently skipping the remote copy and the retention
# enforcement below. Revisit upward as real usage grows.
[ "$size" -ge 4096 ] || fail "dump suspiciously small (${size} bytes): $OUT"

rclone copyto "$OUT" "$REMOTE/$(basename "$OUT")" \
  || fail "rclone copy to $REMOTE failed"

# Verify the remote object by size — the exit code of a copy is not proof.
rsize="$(rclone lsl "$REMOTE/$(basename "$OUT")" 2>/dev/null | awk '{print $1}' | head -1)"
[ "$rsize" = "$size" ] || fail "remote size mismatch (local $size, remote ${rsize:-absent})"

# Prune, remote then local.
rclone delete --min-age "${KEEP_REMOTE}d" "$REMOTE" 2>/dev/null \
  || echo "WARN remote prune command failed — the invariant below decides"
find "$OUTDIR" -name 'visio-*.sql.gz' -mtime +"$KEEP_LOCAL" -delete

# Assert the INVARIANT, not the action: no surviving remote object may be
# older than the retention the privacy policy publishes. A prune that exits 0
# without deleting (wrong prefix, missing DELETE right, clock skew) would
# otherwise leave the published 30 days unenforced and silent — the same
# failure shape as the log-retention promise in 1.1. Two days of slack
# absorbs timezone and run-time drift.
oldest_days="$(rclone lsjson --max-age "$(( KEEP_REMOTE + 2 ))d" "$REMOTE" 2>/dev/null \
  | grep -c '"Path"')"
total="$(rclone lsjson "$REMOTE" 2>/dev/null | grep -c '"Path"')"
if [ "$total" = "0" ]; then
  fail "remote holds no objects after a verified upload — check BACKUP_REMOTE_PATH ($REMOTE)"
elif [ "$oldest_days" != "$total" ]; then
  fail "remote holds $(( total - oldest_days )) object(s) older than ${KEEP_REMOTE}+2 days — the published ${KEEP_REMOTE}-day backup retention is NOT enforced"
fi

date +%s > "$OUTDIR/LAST_OK"
echo "OK $(basename "$OUT") (${size} bytes) verified at $REMOTE"
