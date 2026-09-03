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
#
# Nothing about the app is hardcoded, so the same drill serves the next app
# (Docs) without a fork. Overridable by environment:
#   DRILL_PG_IMAGE  Postgres image to restore INTO. Defaults to the image the
#                   stack itself runs, read from the merged compose config —
#                   restoring a dump into a different major version is the
#                   classic way a drill passes while the real restore fails.
#                   Falling back to a Docker Hub tag also makes the drill fail
#                   on a rate-limited host that has the image locally already.
#   DRILL_DB_USER   Role the dump expects to own its objects. Defaults to
#                   DB_USER from env.d/postgresql.
#   DRILL_TABLES    Space-separated tables to count as the proof that data,
#                   not just schema, came back. Defaults to the Meet tables;
#                   set it for another app. A table that is absent is reported
#                   as such rather than silently counted as zero.

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

# ── Resolve what to restore into, and what to assert on ─────────────────────
# A SQL identifier reaches psql -c unquoted, so both are constrained to the
# identifier grammar rather than trusted because they came from a local file.
ident_ok() { case "$1" in ''|*[!A-Za-z0-9_]*) return 1 ;; *) return 0 ;; esac; }

DB_USER_DEFAULT="$(envval env.d/postgresql DB_USER)"
DRILL_DB_USER="${DRILL_DB_USER:-${DB_USER_DEFAULT:-meet}}"
ident_ok "$DRILL_DB_USER" || fail "DRILL_DB_USER='$DRILL_DB_USER' is not a bare SQL identifier"

DRILL_TABLES="${DRILL_TABLES:-meet_user meet_room}"
for t in $DRILL_TABLES; do
  ident_ok "$t" || fail "DRILL_TABLES entry '$t' is not a bare SQL identifier"
done

# The image the stack actually runs, so the drill restores into the same major
# version the dump came from. `--images` prints one image per service and needs
# no secret resolution; the grep keeps it to the postgres one.
if [ -z "${DRILL_PG_IMAGE:-}" ]; then
  # No --env-file: compose already auto-loads .env from the project directory
  # when there is one, and demanding it would break the drill on a dir that
  # keeps its variables elsewhere.
  DRILL_PG_IMAGE="$(docker compose config --images 2>/dev/null \
                    | grep -m1 -E '(^|/)postgres:' || true)"
  DRILL_PG_IMAGE="${DRILL_PG_IMAGE:-postgres:16}"
fi

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
docker run -d --name "$CONTAINER" -e POSTGRES_PASSWORD=drill "$DRILL_PG_IMAGE" >/dev/null \
  || fail "docker run $DRILL_PG_IMAGE failed"

# Probe over TCP, never the default Unix socket. The postgres entrypoint runs
# initdb against a TEMPORARY server it starts with `listen_addresses=''` and
# then stops with `pg_ctl -m fast` before the real server starts. That
# temporary server accepts SOCKET connections, so `pg_isready` with no -h
# answers "accepting connections" while the database is still initialising:
# the drill would restore into a server about to be shut down, and whichever
# statement it had reached at the handover fails for a reason that has nothing
# to do with the backup. Only the real server ever answers on TCP.
ready=0
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -h 127.0.0.1 -p 5432 -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[ "$ready" -eq 1 ] || fail "postgres in $CONTAINER did not become ready within 60s"

# Keep psql's own stderr in the failure line. Discarding it is what turned the
# readiness race above into "FAIL CREATE ROLE meet failed" with no cause named,
# which is a failure a reader re-runs instead of diagnosing.
#
# Flattened to ONE line, because every assertion against this script — here, in
# CI, and in the runbook — is an anchored ^FAIL grep. psql's errors are
# routinely two lines ("connection to server failed:" then the FATAL that says
# why), so a raw multi-line splice would put the half that explains the failure
# on a continuation line nothing greps, which is the very illegibility this is
# meant to remove.
oneline() { printf '%s' "${1//$'\n'/ }"; }
err="$(docker exec "$CONTAINER" psql -U postgres \
       -c "CREATE ROLE $DRILL_DB_USER LOGIN" 2>&1 >/dev/null)" \
  || fail "CREATE ROLE $DRILL_DB_USER failed${err:+ — $(oneline "$err")}"
err="$(docker exec "$CONTAINER" psql -U postgres \
       -c "CREATE DATABASE drill OWNER $DRILL_DB_USER" 2>&1 >/dev/null)" \
  || fail "CREATE DATABASE drill failed${err:+ — $(oneline "$err")}"

gunzip -c "$DUMP" | docker exec -i "$CONTAINER" psql -q -v ON_ERROR_STOP=1 -U postgres -d drill \
  || fail "restore of $DUMP into drill failed"

migrations="$(docker exec "$CONTAINER" psql -U postgres -d drill -tqc "SELECT count(*) FROM django_migrations" 2>/dev/null | tr -d ' ')"
case "$migrations" in
  ''|*[!0-9]*) fail "django_migrations count query failed against $SOURCE_DESC" ;;
esac
[ "$migrations" -gt 0 ] || fail "django_migrations is empty after restore — schema did not restore correctly ($SOURCE_DESC)"

# Row counts are the proof that DATA came back, not just the schema. A table
# named in DRILL_TABLES that the dump does not contain is a finding, not a
# zero: silently printing "0" is how a drill vouches for an empty restore.
counts=""
for t in $DRILL_TABLES; do
  n="$(docker exec "$CONTAINER" psql -U postgres -d drill -tqc "SELECT count(*) FROM $t" 2>/dev/null | tr -d ' ')"
  case "$n" in
    ''|*[!0-9]*) fail "table $t is absent from the restore of $SOURCE_DESC (DRILL_TABLES expects it)" ;;
  esac
  counts="$counts $t=$n"
done

echo "OK restored from $SOURCE_DESC into $DRILL_PG_IMAGE: $migrations migrations,${counts:- no tables asserted}"
