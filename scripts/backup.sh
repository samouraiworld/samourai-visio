#!/usr/bin/env bash
# Nightly PostgreSQL backup for visio.samourai.app — dump, verify, ship
# off-box, verify the remote copy, and only then touch the freshness marker.
# `backup.sh prune` is the separate, delete-capable half.
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
# Two credentials, two entry points. The nightly dump (the default mode)
# uploads through the `visio` remote, whose key can write and read but NOT
# delete — append-only at the bucket's IAM, which is what makes a backup
# survive the host it protects: the key handled every night, in the process
# that also holds the database dump, can add to the bucket and never empty
# it. `backup.sh prune` runs through the `visioprune` remote, the only key
# that can delete, exported in that mode only. Each mode reads exactly one
# RCLONE_CONFIG_* block from env.d/backup and never the other.
#
# The remote keeps BACKUP_KEEP_REMOTE_DAYS days of dumps — the number the
# privacy policy publishes, so the prune is not housekeeping, it is the
# enforcement of a published retention period. Both modes assert it as an
# INVARIANT (oldest surviving object), never as "the delete exited 0": a
# prune that stopped — cron line gone, key revoked — turns the nightly red
# within two days, and the nightly itself never deletes.
# Restore drill: RUNBOOK §8ter. An untested backup is not a backup.
#
# Usage: run from ~/visio, or set VISIO_DIR. Needs docker compose, rclone,
# and env.d/backup (template: deploy/env.d/backup.example).
#   backup.sh          # dump, upload, verify, assert retention, mark
#   backup.sh prune    # delete remote dumps past retention, assert retention

set -uo pipefail
# The dump and the marker carry every user's email and room metadata. cron's
# default umask is 022, which would leave them 0644 — world-readable PII for
# as long as the local copies live.
umask 077
MODE="${1:-backup}"
case "$MODE" in
  backup|prune) ;;
  *) echo "usage: $0 [backup|prune]"; exit 2 ;;
esac
DIR="${VISIO_DIR:-$PWD}"
cd "$DIR" || { echo "FAIL cannot cd to $DIR"; exit 1; }

fail() { echo "FAIL $1"; exit 1; }
# Read a value from an env file without sourcing it (never executes content).
envval() { grep -m1 "^$2=" "$1" 2>/dev/null | cut -d= -f2- | sed 's/^"//; s/"$//'; }

[ -f env.d/backup ] || fail "env.d/backup missing (template: deploy/env.d/backup.example)"
command -v rclone >/dev/null 2>&1 || fail "rclone not installed (apt-get install rclone)"

# Export ONE remote definition, never both, without sourcing the file: the
# write key in backup mode, the delete key in prune mode. Nothing else in
# the file is evaluated. `RCLONE_CONFIG_VISIO_` does not match the
# `RCLONE_CONFIG_VISIOPRUNE_` block — the underscore is the separator.
case "$MODE" in
  backup) PREFIX="RCLONE_CONFIG_VISIO_" ;;
  prune)  PREFIX="RCLONE_CONFIG_VISIOPRUNE_" ;;
esac
# shellcheck disable=SC2163  # dynamic export; the key is validated by grep + case
while IFS='=' read -r k v; do
  case "$k" in
    "$PREFIX"*) export "$k=$v" ;;
  esac
done < <(grep -E "^${PREFIX}[A-Z0-9_]+=" env.d/backup)

REMOTE="$(envval env.d/backup BACKUP_REMOTE_PATH)"
KEEP_LOCAL="$(envval env.d/backup BACKUP_KEEP_LOCAL_DAYS)"; KEEP_LOCAL="${KEEP_LOCAL:-7}"
KEEP_REMOTE="$(envval env.d/backup BACKUP_KEEP_REMOTE_DAYS)"; KEEP_REMOTE="${KEEP_REMOTE:-30}"
[ -n "$REMOTE" ] || fail "BACKUP_REMOTE_PATH unset in env.d/backup"
case "$REMOTE" in
  *"<"*) fail "env.d/backup still carries a <placeholder>" ;;
  *:*) : ;;
  *) fail "BACKUP_REMOTE_PATH is not remote:bucket/prefix ($REMOTE)" ;;
esac
# The same bucket and prefix, through the delete-capable remote.
PRUNE_REMOTE="visioprune:${REMOTE#*:}"

# Assert the INVARIANT, not the action: no surviving remote object may be
# older than the retention the privacy policy publishes. A prune that exits 0
# without deleting (wrong prefix, missing DELETE right, clock skew) would
# otherwise leave the published 30 days unenforced and silent — the same
# failure shape as the log-retention promise in 1.1. Two days of slack
# absorbs timezone and run-time drift, and the gap between the nightly dump
# and the nightly prune.
assert_retention() {
  local remote="$1" young total
  young="$(rclone lsjson --max-age "$(( KEEP_REMOTE + 2 ))d" "$remote" 2>/dev/null | grep -c '"Path"')"
  total="$(rclone lsjson "$remote" 2>/dev/null | grep -c '"Path"')"
  if [ "$total" = "0" ]; then
    fail "remote holds no objects ($remote) — check BACKUP_REMOTE_PATH and the key's list right"
  elif [ "$young" != "$total" ]; then
    fail "remote holds $(( total - young )) object(s) older than ${KEEP_REMOTE}+2 days — the published ${KEEP_REMOTE}-day backup retention is NOT enforced (is \`backup.sh prune\` scheduled, with a key that can delete?)"
  fi
  RETENTION_TOTAL="$total"
}
RETENTION_TOTAL=0

if [ "$MODE" = "prune" ]; then
  [ -n "$(envval env.d/backup "${PREFIX}TYPE")" ] \
    || fail "env.d/backup defines no ${PREFIX}* remote — the prune has no credential of its own (template: deploy/env.d/backup.example)"
  # Loud on the command here, unlike the nightly: this key exists to delete,
  # so a refusal is a credential or path problem worth seeing on day one,
  # not on the day the invariant below finally trips.
  rclone delete --min-age "${KEEP_REMOTE}d" "$PRUNE_REMOTE" \
    || fail "rclone delete on $PRUNE_REMOTE failed — the prune key cannot delete there, or the path is wrong"
  assert_retention "$PRUNE_REMOTE"
  echo "OK prune: $PRUNE_REMOTE holds $RETENTION_TOTAL object(s), none older than ${KEEP_REMOTE}+2 days"
  exit 0
fi

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

# Local prune only. The remote is never deleted from here: this process
# holds the write key, and the write key cannot delete — `backup.sh prune`
# is the other half, with the other key.
find "$OUTDIR" -name 'visio-*.sql.gz' -mtime +"$KEEP_LOCAL" -delete

assert_retention "$REMOTE"

date +%s > "$OUTDIR/LAST_OK"
echo "OK $(basename "$OUT") (${size} bytes) verified at $REMOTE"
