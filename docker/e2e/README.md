# Local browser acceptance runtime

Status: Verified locally

The same `bin/test-e2e-local` command runs locally and in CI. It builds the
application from the checked-out source, migrates a fresh PostgreSQL database,
seeds test sessions, and exercises the built frontend against real Django,
Redis, LiveKit, Celery worker and Beat processes. Authentication fixtures are
local sessions; this suite does not contact an identity provider. The
[scenario specification](../../src/e2e/README.md) defines acceptance coverage.

Acceptance: `bin/test-e2e-local` must pass the browser scenarios and return a
nonzero exit code for a failing scenario. A run has its own Compose project and
temporary volumes, publishes no host ports, and removes its containers and
volumes on exit. Logs, fixture metadata, browser reports and traces remain in
the printed artifact directory. `docker/e2e/test-runner.sh` injects browser,
build, startup and cleanup failures to verify the runner preserves failure
status and always collects logs and removes its resources.
`bin/test-e2e-local --help` documents options.

The browser and media server share a Docker network. Chromium reaches the
frontend at its own `http://localhost:3000` (a secure browser context for fake
media devices), with API traffic proxied to Django and WebRTC using LiveKit's
private container address. No external TURN server or production credentials
are used. Dependency downloads and base image pulls require network access on
the first build; the test application runs entirely in Docker.

Runtime versions follow the upstream development services: PostgreSQL 16,
Redis 5 and LiveKit 1.13.6. Playwright's package and browser image both use
1.63.0. Node 22 matches the upstream frontend CI runtime. The backend installs
the committed uv lockfile, and both JavaScript
projects install their committed npm lockfiles.
