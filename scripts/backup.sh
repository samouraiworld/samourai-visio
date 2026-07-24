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
# privacy policy publishes. Restore drill: RUNBOOK §8ter. An untested backup
# is not a backup.
#
# Usage: run from ~/visio, or set VISIO_DIR. Needs docker compose, rclone,
# and env.d/backup (template: deploy/env.d/backup.example).

set -uo pipefail
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
OUT="$OUTDIR/visio-$(date +%F-%H%M).sql.gz"

docker compose exec -T postgresql pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$OUT" \
  || fail "pg_dump exited non-zero"

# The dump must gunzip cleanly, start like a pg_dump, and have plausible mass.
gunzip -t "$OUT" 2>/dev/null || fail "not a valid gzip: $OUT"
gunzip -c "$OUT" 2>/dev/null | head -3 | grep -q "PostgreSQL database dump" \
  || fail "dump lacks the pg_dump header: $OUT"
size="$(wc -c < "$OUT" | tr -d ' ')"
[ "$size" -ge 10240 ] || fail "dump suspiciously small (${size} bytes): $OUT"

rclone copyto "$OUT" "$REMOTE/$(basename "$OUT")" \
  || fail "rclone copy to $REMOTE failed"

# Verify the remote object by size — the exit code of a copy is not proof.
rsize="$(rclone lsl "$REMOTE/$(basename "$OUT")" 2>/dev/null | awk '{print $1}' | head -1)"
[ "$rsize" = "$size" ] || fail "remote size mismatch (local $size, remote ${rsize:-absent})"

# Prune, remote then local. A failed prune is a warning, not a failed backup.
rclone delete --min-age "${KEEP_REMOTE}d" "$REMOTE" 2>/dev/null \
  || echo "WARN remote prune failed (the backup itself is fine)"
find "$OUTDIR" -name 'visio-*.sql.gz' -mtime +"$KEEP_LOCAL" -delete

date +%s > "$OUTDIR/LAST_OK"
echo "OK $(basename "$OUT") (${size} bytes) verified at $REMOTE"
