# Run CI and browser acceptance locally

Status: Verified locally

```sh
make test-ci-local
```

This runs the checks from `.github/workflows/ci.yml` and then the browser
acceptance suite. The workflow inherits the upstream
[`suitenumerique/meet` CI](https://github.com/suitenumerique/meet/blob/main/.github/workflows/ci.yml).
The runner reads its shell steps directly, including this fork's additional
checks; there is no second list of lint, test, or build commands to maintain.

On macOS or Linux, install Docker with Compose v2, Git, and Python 3 on the host.
Docker must be running and able to download public images. The first run also
downloads locked application dependencies; tests execute locally and need no GitHub token,
deployment credentials, paid services, or existing development stack.

Use a current local PR base ref. The default is `origin/develop`; fetch it first
when needed. To choose another base or run only the CI checks:

```sh
bin/test-ci-local --base origin/develop --skip-e2e
```

Run only the browser suite with `make test-e2e-local`. See
[`docker/e2e/README.md`](../docker/e2e/README.md) for its scenarios, diagnostics,
and browser runtime requirements.

## Isolation and results

The CI command creates a temporary checkout containing current Git-visible files,
including uncommitted changes. Ignored files—including local credential files,
installed dependencies, and development data—are excluded. A short initializer
copies that snapshot into an isolated Docker volume; package installation and
tests use the volume to avoid shared-filesystem overhead on macOS. Build outputs stay in that volume.
The Git history checks inspect existing commits against the chosen base. Local
runs use pull-request context without the `noChangeLog` label exemption.

Checks run as the host UID/GID, preserving the permission behavior needed by
unreadable-file mutation tests. Each invocation gets a separate Docker project,
network, PostgreSQL database, Redis instance, and MinIO bucket. Services publish
no host ports. Cleanup removes only this invocation's containers, network, volumes, and temporary checkout, even
when a test fails or the run is interrupted. Dependency build layers may remain
in Docker's cache.

The printed results directory contains a log for each job and `results.json`.
A failed job or blocked dependency produces a nonzero exit status. Independent
jobs still run, making one invocation useful for finding failures across the
whole repository. Browser results are retained by the browser runner separately.

## CI correspondence

| Hosted checks | Local execution |
| --- | --- |
| Commit rules and changelog | Original Git history and workflow shell commands |
| Mail templates | Node 22 and `npm ci` against the mail package lock |
| Backend lint and tests | Python 3.13, locked uv dependencies, real PostgreSQL 16, Redis 5, and MinIO |
| Agent lint | Full locked agent dependencies and upstream lint commands |
| Summary lint and tests | Python 3.13, locked dependencies, ffmpeg |
| Frontend lint, types, tests, build | Node 22 and `npm ci`, including typecheck mutation test |
| SDK lint and build | Node 22 and locked npm dependencies |
| Helm runtime invariants | Helm 3.19.0, including negative storage mutations |
| Repository attribution policy | Existing checker and its mutation self-test |
| Browser acceptance | The same standalone entry points used by the browser CI job |

The Linux image uses Debian Bookworm on the host's CPU architecture. Hosted CI
uses Ubuntu; this is command and service parity, not an emulator for every
GitHub Actions feature. Checkout, tool installation, and caching actions map to
the temporary checkout and preinstalled tools. MinIO provisioning and OS package
installation map to Compose health checks and the image build. The mail job uses
its committed npm lockfile; upstream's Yarn command has no Yarn lockfile in this checkout. Mail templates are always rebuilt instead of
restoring a hosted cache.

Unsupported actions, conditions, expressions, runtime versions, service images,
and changed infrastructure setup commands fail before the jobs run. When changing
the workflow, update the explicit adapter only if new hosted infrastructure needs
a local equivalent. Ordinary added shell commands execute automatically.

```sh
python3 -m unittest discover -s docker/ci/tests
```

These fast mutation tests prove the adapter rejects unsupported changes. They
also run inside the local CI image before application checks.
