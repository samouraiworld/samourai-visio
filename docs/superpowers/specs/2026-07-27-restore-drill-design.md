# restore-drill.sh — design

## Purpose

RUNBOOK.md §8ter documents a manual "restore drill" — a sequence of shell
commands run by hand to prove a backup dump actually restores. An untested
backup is not a backup, but a manual, undocumented-as-code procedure is easy
to skip or run wrong. This turns that procedure into `scripts/restore-drill.sh`,
matching the conventions already established by `scripts/backup.sh` and
`scripts/preflight.sh`: assert on output, fail loud, exit non-zero.

## Usage

```
scripts/restore-drill.sh [--remote]
```

Run from `~/visio`, or with `VISIO_DIR` set — same convention as `backup.sh`.

- No flag (default): restore the most recent local dump, `~/backups/visio-*.sql.gz`.
- `--remote`: download the most recent object from the off-box bucket via
  `rclone` (reads `BACKUP_REMOTE_PATH` from `env.d/backup`, same as
  `backup.sh`) into a temp file, and restore that instead.

The default is local (fast, no network dependency, matches the drill as
currently documented). `--remote` is the more complete test — it is the only
way to prove the bucket copy, not just the local file, is actually
restorable — and should be the one run after a PostgreSQL major-version bump
per RUNBOOK §8ter.

## Steps

1. Resolve `VISIO_DIR`, `cd` there (same pattern as `backup.sh`).
2. Parse `--remote`/no-flag.
3. Resolve the dump to restore:
   - local: `ls -1t ~/backups/visio-*.sql.gz | head -1`; fail if none found.
   - remote: `rclone lsjson` the remote path, pick the newest object,
     `rclone copyto` it to a temp file under a private (`chmod 700`) temp dir;
     fail if the remote holds no objects.
4. `docker rm -f restore-drill 2>/dev/null || true` — clear a container left
   over from a previous crashed run before starting a fresh one.
5. `docker run -d --name restore-drill -e POSTGRES_PASSWORD=drill postgres:16`
   (same tag as `compose.yaml`'s `postgresql` service — the restore drill's
   whole point is fidelity to what production actually runs).
6. Wait for readiness by polling `docker exec restore-drill pg_isready -U postgres`
   in a loop with a timeout (e.g. 30s), instead of a fixed `sleep 5` — condition
   based, not time based, consistent with the "assert on output" rule already
   documented in `backup.sh`. Fail on timeout.
7. `CREATE ROLE meet LOGIN`, `CREATE DATABASE drill OWNER meet` — fail loud if
   either exits non-zero.
8. `gunzip -c "$DUMP" | docker exec -i restore-drill psql -q -v ON_ERROR_STOP=1 -U postgres -d drill`
   with `set -o pipefail` so a SIGPIPE or a mid-restore SQL error surfaces
   instead of being swallowed by the pipe's exit code.
9. Assertions, run after the restore completes:
   - `SELECT count(*) FROM django_migrations` — **hard fail** if the query
     errors or returns `0`. This table exists in every Meet dump regardless
     of real usage, so it is a structural invariant: the schema restored
     correctly.
   - `SELECT count(*) FROM meet_user` and `SELECT count(*) FROM meet_room` —
     captured and reported, **not** hard-failed on zero. They are evidence
     the real business data came back, but a zero count on a genuinely fresh
     instance would not be a restore failure, so they stay informational.
10. Clean up: `docker rm -f restore-drill` and the remote temp file (if any),
    via a `trap ... EXIT` so cleanup runs on both success and failure paths,
    not just the happy path.
11. On success: `OK restored from <local|remote> <dump-name>: N migrations, N users, N rooms`.
    On any failure: `FAIL <reason>`, matching `backup.sh`'s `fail()` helper,
    exit non-zero.

## Out of scope

- No flag to keep the drill container running for manual poking — the drill
  is meant to be a fast, repeatable assertion, not an interactive session.
- No comparison against a previous drill's counts — that's what the backup
  size floor (`backup.sh`) and the retention invariant already cover; this
  script's job is narrowly "does this dump restore cleanly."

## Documentation

RUNBOOK.md §8ter's inline command block is replaced with a pointer to
`scripts/restore-drill.sh [--remote]`, keeping the rationale prose (why the
role must pre-exist, why `django_migrations` is the invariant) but removing
the now-duplicated shell commands.
