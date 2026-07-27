# restore-drill.sh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the manual restore drill documented in `RUNBOOK.md` §8ter into `scripts/restore-drill.sh`, a repeatable, fail-loud script matching `scripts/backup.sh`'s conventions.

**Architecture:** A single bash script, run from `~/visio` (or `VISIO_DIR`). It resolves a dump (local, by default, or `--remote` via `rclone`), spins up a disposable `postgres:16` container, restores into it, asserts the restore actually worked, and always cleans the container up via a `trap`. No new dependencies beyond what `backup.sh` already requires (`docker`, and `rclone` only for `--remote`).

**Tech Stack:** bash, docker, psql (inside the container), rclone (remote mode only).

## Global Constraints

- Usage: `scripts/restore-drill.sh [--remote]`. No flag = local (this repo's chosen default).
- `postgres:16` — same tag as `compose.yaml`'s `postgresql` service. Do not drift from it.
- Container name is the fixed string `restore-drill`; it is force-removed both before starting (clears a leftover from a crashed prior run) and on exit via `trap ... EXIT` (success or failure).
- Wait for container readiness by polling `pg_isready` in a loop (max 30 iterations, 1s apart) — never a fixed `sleep`.
- `CREATE ROLE meet LOGIN` and `CREATE DATABASE drill OWNER meet` must run, and fail loud on error, before the restore — the dump carries `ALTER ... OWNER TO meet`, so the role must pre-exist.
- Restore via `gunzip -c "$DUMP" | docker exec -i restore-drill psql -q -v ON_ERROR_STOP=1 -U postgres -d drill`, under `set -uo pipefail` so a mid-restore SQL error is not swallowed.
- `django_migrations` count: **hard fail** (via the existing `fail()` helper: `echo "FAIL $1"; exit 1`) if the query errors or returns `0`.
- `meet_user` / `meet_room` counts: captured and printed in the final `OK` line, never hard-failed on zero.
- Every failure path prints `FAIL <reason>` and exits non-zero; success prints `OK restored from <local|remote> <source>: N migrations, N users, N rooms`.
- `RUNBOOK.md` §8ter's inline command block is replaced with a pointer to the script, keeping the existing rationale prose.

---

### Task 1: Core script — local mode

**Files:**
- Create: `scripts/restore-drill.sh`
- Test: manual invocation from a shell (no test framework exists in this repo — `backup.sh` and `preflight.sh` are verified the same way, by running them for real and reading their `OK`/`FAIL` output)

**Interfaces:**
- Produces (used by Task 2): the `fail()` helper, the `envval()` helper (copy verbatim from `scripts/backup.sh:33-35`), the `CONTAINER="restore-drill"` variable, the `cleanup()` function registered via `trap cleanup EXIT`, and the two variables every later step relies on: `DUMP` (path to the gzip to restore) and `SOURCE_DESC` (human-readable string describing where it came from, e.g. `local /root/backups/visio-2026-07-27-1709.sql.gz`).
- Consumes: nothing from other tasks (this task stands alone for the local path).

- [ ] **Step 1: Write the script with local-mode dump resolution, container lifecycle, restore, and assertions**

Create `scripts/restore-drill.sh`:

```bash
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
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  [ -n "$TMPFILE" ] && rm -f "$TMPFILE"
}
trap cleanup EXIT

if [ "$MODE" = "local" ]; then
  DUMP="$(ls -1t "$HOME/backups"/visio-*.sql.gz 2>/dev/null | head -1)"
  [ -n "$DUMP" ] || fail "no local dump found in $HOME/backups"
  SOURCE_DESC="local $DUMP"
else
  fail "remote mode not implemented yet"
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
```

Make it executable:

```bash
chmod +x scripts/restore-drill.sh
```

- [ ] **Step 2: Verify bash syntax**

Run: `bash -n scripts/restore-drill.sh`
Expected: no output (exits 0).

- [ ] **Step 3: Build a synthetic dump fixture and confirm the happy path**

No pg_dump/docker-compose stack is required for this test — a minimal
hand-built dump exercises the same mechanics (role-must-exist-first,
restore, assertions) that a real Meet dump would.

```bash
mkdir -p "$HOME/backups"
cat > /tmp/fixture.sql <<'EOF'
--
-- PostgreSQL database dump
--
CREATE TABLE django_migrations (id serial, app text, name text, applied timestamptz);
ALTER TABLE django_migrations OWNER TO meet;
INSERT INTO django_migrations (app, name, applied) VALUES ('contenttypes', '0001_initial', now());
CREATE TABLE meet_user (id text, email text);
ALTER TABLE meet_user OWNER TO meet;
INSERT INTO meet_user (id, email) VALUES ('u1', 'test@example.com');
CREATE TABLE meet_room (name text, slug text);
ALTER TABLE meet_room OWNER TO meet;
INSERT INTO meet_room (name, slug) VALUES ('room1', 'room1');
EOF
gzip -c /tmp/fixture.sql > "$HOME/backups/visio-9999-01-01-0000.sql.gz"
VISIO_DIR="$PWD" scripts/restore-drill.sh
```

Expected: `OK restored from local /home/<you>/backups/visio-9999-01-01-0000.sql.gz: 1 migrations, 1 users, 1 rooms`

Then confirm cleanup actually ran:

```bash
docker ps -a --filter name=restore-drill --format '{{.Names}}'
```

Expected: empty output (no leftover container).

- [ ] **Step 4: Confirm the hard-fail path — schema restores but no migrations row**

```bash
cat > /tmp/fixture-empty.sql <<'EOF'
--
-- PostgreSQL database dump
--
CREATE TABLE django_migrations (id serial, app text, name text, applied timestamptz);
ALTER TABLE django_migrations OWNER TO meet;
CREATE TABLE meet_user (id text, email text);
ALTER TABLE meet_user OWNER TO meet;
CREATE TABLE meet_room (name text, slug text);
ALTER TABLE meet_room OWNER TO meet;
EOF
gzip -c /tmp/fixture-empty.sql > "$HOME/backups/visio-9999-01-01-0001.sql.gz"
VISIO_DIR="$PWD" scripts/restore-drill.sh
```

Expected: `FAIL django_migrations is empty after restore — schema did not restore correctly (local /home/<you>/backups/visio-9999-01-01-0001.sql.gz)` and non-zero exit (`echo $?` shows `1`). The most-recent-mtime fixture is picked automatically since it was written last.

- [ ] **Step 5: Clean up the fixtures**

```bash
rm -f "$HOME/backups"/visio-9999-*.sql.gz /tmp/fixture.sql /tmp/fixture-empty.sql
```

- [ ] **Step 6: Commit**

```bash
git add scripts/restore-drill.sh
git commit -m "$(cat <<'EOF'
Add scripts/restore-drill.sh (local mode)

Turns the manual restore drill in RUNBOOK.md §8ter into a repeatable
script: spins up a disposable postgres:16 container, restores the most
recent local dump, and hard-fails if django_migrations comes back empty.
EOF
)"
```

---

### Task 2: `--remote` mode

**Files:**
- Modify: `scripts/restore-drill.sh` (replace the `else fail "remote mode not implemented yet"` branch from Task 1)

**Interfaces:**
- Consumes from Task 1: `fail()`, `envval()`, `MODE`, `TMPFILE` (already declared, currently unused), and must set the same two variables Task 1's local branch sets: `DUMP` and `SOURCE_DESC`.
- Produces: nothing new for later tasks — Task 3 only touches `RUNBOOK.md`.

This task needs `rclone` installed to test for real. If it isn't available on
your machine (`command -v rclone`), install it first — it's the same
dependency `backup.sh` already requires (`deploy/host` install notes):

```bash
sudo apt-get install -y rclone   # Debian/Ubuntu
sudo dnf install -y rclone       # Fedora
```

- [ ] **Step 1: Implement remote dump resolution**

Replace the `else` branch in `scripts/restore-drill.sh`:

```bash
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

  latest="$(rclone lsjson "$REMOTE" 2>/dev/null \
    | grep -o '"Path":"[^"]*visio-[^"]*\.sql\.gz"' \
    | sed 's/.*:"//; s/"$//' \
    | sort \
    | tail -1)"
  [ -n "$latest" ] || fail "remote holds no visio-*.sql.gz objects ($REMOTE)"

  restore_tmpdir="$(mktemp -d)"
  chmod 700 "$restore_tmpdir"
  TMPFILE="$restore_tmpdir/$latest"
  rclone copyto "$REMOTE/$latest" "$TMPFILE" || fail "rclone copy of $latest from $REMOTE failed"
  DUMP="$TMPFILE"
  SOURCE_DESC="remote $REMOTE/$latest"
fi
```

- [ ] **Step 2: Verify bash syntax**

Run: `bash -n scripts/restore-drill.sh`
Expected: no output.

- [ ] **Step 3: Confirm remote-mode happy path against a local rclone "remote"**

`rclone` can treat a plain directory as a remote without any cloud
credentials, which is enough to test the download-and-restore mechanics:

```bash
mkdir -p /tmp/fake-bucket
cat > /tmp/fixture-remote.sql <<'EOF'
--
-- PostgreSQL database dump
--
CREATE TABLE django_migrations (id serial, app text, name text, applied timestamptz);
ALTER TABLE django_migrations OWNER TO meet;
INSERT INTO django_migrations (app, name, applied) VALUES ('contenttypes', '0001_initial', now());
CREATE TABLE meet_user (id text, email text);
ALTER TABLE meet_user OWNER TO meet;
INSERT INTO meet_user (id, email) VALUES ('u1', 'test@example.com');
CREATE TABLE meet_room (name text, slug text);
ALTER TABLE meet_room OWNER TO meet;
INSERT INTO meet_room (name, slug) VALUES ('room1', 'room1');
EOF
gzip -c /tmp/fixture-remote.sql > /tmp/fake-bucket/visio-2026-01-01-0000.sql.gz
mkdir -p env.d
cat > env.d/backup <<'EOF'
BACKUP_REMOTE_PATH=/tmp/fake-bucket:
BACKUP_KEEP_LOCAL_DAYS=7
BACKUP_KEEP_REMOTE_DAYS=30
EOF
VISIO_DIR="$PWD" scripts/restore-drill.sh --remote
```

Note: `rclone`'s local backend is addressed as a plain path, so
`BACKUP_REMOTE_PATH=/tmp/fake-bucket` (no `remote:` prefix needed) — adjust
the value above to whatever `rclone lsjson /tmp/fake-bucket` accepts on your
installed rclone version; confirm with `rclone lsjson /tmp/fake-bucket`
before running the drill.

Expected: `OK restored from remote /tmp/fake-bucket/visio-2026-01-01-0000.sql.gz: 1 migrations, 1 users, 1 rooms`

- [ ] **Step 4: Clean up the fixture env file and fake bucket**

```bash
rm -rf /tmp/fake-bucket
rm -f env.d/backup   # only if this repo checkout has no real one — check `git status` first
```

- [ ] **Step 5: Commit**

```bash
git add scripts/restore-drill.sh
git commit -m "$(cat <<'EOF'
Add --remote mode to restore-drill.sh

Downloads the most recent dump from the off-box bucket (env.d/backup,
same rclone config as backup.sh) instead of using the local copy — the
only way to prove the copy that would survive losing this host is
itself restorable.
EOF
)"
```

---

### Task 3: Update RUNBOOK.md §8ter

**Files:**
- Modify: `RUNBOOK.md:653-669` (the "restore drill" subsection)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Replace the inline command block with a pointer to the script**

Replace the current block (`RUNBOOK.md:653-669`):

```markdown
### The restore drill — an untested backup is not a backup

Run once now, and after any PostgreSQL major-version bump:

```bash
L="$(ls -1t ~/backups/visio-*.sql.gz | head -1)"
docker run -d --name restore-drill -e POSTGRES_PASSWORD=drill postgres:16
sleep 5
# The dump carries ALTER ... OWNER TO meet — the role must exist first.
docker exec restore-drill psql -U postgres -c "CREATE ROLE meet LOGIN"
docker exec restore-drill psql -U postgres -c "CREATE DATABASE drill OWNER meet"
gunzip -c "$L" | docker exec -i restore-drill psql -q -v ON_ERROR_STOP=1 -U postgres -d drill
docker exec restore-drill psql -U postgres -d drill -tc "SELECT count(*) FROM django_migrations"
# Expect a non-zero count — django_migrations exists in every Meet dump, so
# zero rows or an error means the restore did NOT work. Then clean up:
docker rm -f restore-drill
```
```

with:

```markdown
### The restore drill — an untested backup is not a backup

Run once now, and after any PostgreSQL major-version bump:

```bash
scripts/restore-drill.sh            # restores the most recent LOCAL dump
scripts/restore-drill.sh --remote   # restores the most recent dump from the bucket
```

Spins up a disposable `postgres:16` container (the role must pre-exist
because the dump carries `ALTER ... OWNER TO meet`), restores into it, and
hard-fails if `django_migrations` comes back empty or errors — that table
exists in every Meet dump regardless of real usage, so its absence means
the restore did not work. The container is always removed on exit, success
or failure. `meet_user`/`meet_room` counts are reported for information but
never fail the drill on their own — a zero count only means the instance
was young when the dump was taken.
```
```

- [ ] **Step 2: Confirm the reference at RUNBOOK.md:681 still reads correctly**

Read `RUNBOOK.md:681` — it currently says *"Backups: run the §8ter install
block, then the restore drill."* No change needed there; just confirm after
editing that the section number/anchor text still matches (§8ter heading
untouched).

- [ ] **Step 3: Commit**

```bash
git add RUNBOOK.md
git commit -m "$(cat <<'EOF'
Point RUNBOOK §8ter at scripts/restore-drill.sh

Replaces the inline restore-drill commands with the scripted version
from the previous two commits, keeping the rationale prose.
EOF
)"
```
