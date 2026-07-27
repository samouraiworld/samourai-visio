#!/usr/bin/env bash
# Restore drill for visio.samourai.app — proves the most recent backup dump
# actually restores. An untested backup is not a backup (RUNBOOK.md §8ter).
#
# Usage: scripts/restore-drill.sh [--remote]
#   (no flag) restores the most recent LOCAL dump under ~/backups.
#   --remote   downloads and restores the most recent dump from the off-box
#              bucket instead (env.d/backup) — the only way to prove the
#              copy that would survive losing this host is itself restorable.
#
# Same design rules as backup.sh: assert on OUTPUT, fail loud, never trust
# an exit code alone when the output can be read directly.
#
# Run from ~/visio, or set VISIO_DIR. Needs docker; --remote also needs
# rclone and env.d/backup (template: deploy/env.d/backup.example).

set -uo pipefail
DIR="${VISIO_DIR:-$PWD}"
cd "$DIR" || { echo "FAIL cannot cd to $DIR"; exit 1; }

fail() { echo "FAIL $1"; exit 1; }
# Read a value from an env file without sourcing it (never executes content).
envval() { grep -m1 "^$2=" "$1" 2>/dev/null | cut -d= -f2- | sed 's/^"//; s/"$//'; }

MODE="local"
case "${1:-}" in
  --remote) MODE="remote" ;;
  "") : ;;
  *) fail "unknown argument: $1 (usage: restore-drill.sh [--remote])" ;;
esac

CONTAINER="restore-drill"
TMPFILE=""
RESTORE_TMPDIR=""
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  [ -n "$RESTORE_TMPDIR" ] && rm -rf "$RESTORE_TMPDIR"
}
trap cleanup EXIT

if [ "$MODE" = "local" ]; then
  # shellcheck disable=SC2012  # names are backup.sh's own visio-%F-%H%M.sql.gz output, never arbitrary/attacker-controlled
  DUMP="$(ls -1t "$HOME/backups"/visio-*.sql.gz 2>/dev/null | head -1)"
  [ -n "$DUMP" ] || fail "no local dump found in $HOME/backups"
  SOURCE_DESC="local $DUMP"
else
  [ -f env.d/backup ] || fail "env.d/backup missing (template: deploy/env.d/backup.example)"
  command -v rclone >/dev/null 2>&1 || fail "rclone not installed (apt-get install rclone)"

  # shellcheck disable=SC2163  # dynamic export; the key is validated by grep + case
  while IFS='=' read -r k v; do
    case "$k" in
      RCLONE_CONFIG_VISIO_*) export "$k=$v" ;;
    esac
  done < <(grep -E '^RCLONE_CONFIG_VISIO_[A-Z0-9_]+=' env.d/backup)

  REMOTE="$(envval env.d/backup BACKUP_REMOTE_PATH)"
  [ -n "$REMOTE" ] || fail "BACKUP_REMOTE_PATH unset in env.d/backup"
  case "$REMOTE" in
    *"<"*) fail "env.d/backup still carries a <placeholder>" ;;
    *:*) : ;;
    *) fail "BACKUP_REMOTE_PATH is not remote:bucket/prefix ($REMOTE)" ;;
  esac

  rclone_err_file="$(mktemp)"
  latest="$(rclone lsf "$REMOTE" 2>"$rclone_err_file" | grep -E 'visio-.*\.sql\.gz$' | sort | tail -1)"
  if [ -z "$latest" ]; then
    err="$(cat "$rclone_err_file" 2>/dev/null)"
    rm -f "$rclone_err_file"
    fail "remote holds no visio-*.sql.gz objects ($REMOTE)${err:+ — rclone: $err}"
  fi
  rm -f "$rclone_err_file"

  RESTORE_TMPDIR="$(mktemp -d)"
  chmod 700 "$RESTORE_TMPDIR"
  TMPFILE="$RESTORE_TMPDIR/$latest"
  rclone copyto "$REMOTE/$latest" "$TMPFILE" || fail "rclone copy of $latest from $REMOTE failed"
  DUMP="$TMPFILE"
  SOURCE_DESC="remote $REMOTE/$latest"
fi

[ -s "$DUMP" ] || fail "dump is empty: $DUMP"

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" -e POSTGRES_PASSWORD=drill postgres:16 >/dev/null \
  || fail "docker run postgres:16 failed"

ready=0
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[ "$ready" -eq 1 ] || fail "postgres in $CONTAINER did not become ready within 30s"

docker exec "$CONTAINER" psql -U postgres -c "CREATE ROLE meet LOGIN" >/dev/null 2>&1 \
  || fail "CREATE ROLE meet failed"
docker exec "$CONTAINER" psql -U postgres -c "CREATE DATABASE drill OWNER meet" >/dev/null 2>&1 \
  || fail "CREATE DATABASE drill failed"

gunzip -c "$DUMP" | docker exec -i "$CONTAINER" psql -q -v ON_ERROR_STOP=1 -U postgres -d drill \
  || fail "restore of $DUMP into drill failed"

migrations="$(docker exec "$CONTAINER" psql -U postgres -d drill -tqc "SELECT count(*) FROM django_migrations" 2>/dev/null | tr -d ' ')"
case "$migrations" in
  ''|*[!0-9]*) fail "django_migrations count query failed against $SOURCE_DESC" ;;
esac
[ "$migrations" -gt 0 ] || fail "django_migrations is empty after restore — schema did not restore correctly ($SOURCE_DESC)"

users="$(docker exec "$CONTAINER" psql -U postgres -d drill -tqc "SELECT count(*) FROM meet_user" 2>/dev/null | tr -d ' ')"
rooms="$(docker exec "$CONTAINER" psql -U postgres -d drill -tqc "SELECT count(*) FROM meet_room" 2>/dev/null | tr -d ' ')"

echo "OK restored from $SOURCE_DESC: $migrations migrations, ${users:-?} users, ${rooms:-?} rooms"
