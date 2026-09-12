# Local CI acceptance contract

Status: Complete; all 14 inherited CI jobs passed locally

The local command must run the pull-request checks from the repository's CI
workflow, which inherits upstream `suitenumerique/meet` CI. It must test the
current working files, including uncommitted changes, without changing the
checkout, reusing development service data, or requiring GitHub credentials.

Acceptance:

- `bin/test-ci-local --skip-e2e` executes every CI job except the separately
  managed browser job, using the workflow's own shell commands.
- The default command also executes `bin/test-e2e-local`.
- Python 3.13, Node 22, PostgreSQL 16, Redis 5, MinIO, gettext, ffmpeg, and Helm
  run inside Linux containers. Each invocation gets its own network and data.
- Failed jobs produce a nonzero exit code and retained logs. Cleanup runs on
  success, failure, and interruption. It only removes this invocation's stack.
- Unknown workflow actions, expressions, conditions, and incompatible runtime
  versions fail visibly rather than silently omitting checks.
- `python3 -m unittest discover -s docker/ci/tests` proves these guardrails reject
  independent mutations before the full run.

Usage and CI correspondence: [`docs/local-ci.md`](../../docs/local-ci.md).

Verification includes 1,360 passing backend tests (one existing expected failure),
54 summary tests, 91 frontend tests, and all lint/build/policy jobs. Browser
acceptance is tracked separately by its own suite.

The runtime runs checks as the host UID/GID: running as root would invalidate
unreadable-file mutation tests. A seeded Docker volume keeps dependency and
source I/O inside Linux. Mail builds now use the committed npm lockfile instead
of invoking Yarn without a Yarn lockfile.
