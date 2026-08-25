# Contributing

This repository holds **deployment configuration only** — no application code.
The application is [La Suite Meet](https://github.com/suitenumerique/meet), run
from unmodified upstream images. See [NOTICE.md](NOTICE.md).

## The one thing to internalise

**Most misconfigurations here fail silently.** Django ignores unknown
environment variables. A list written as JSON parses into nonsense. A missing
bind-mount returns `200 text/html` instead of a 404. Dead CSS tokens apply
cleanly and do nothing.

In every one of those cases you get a healthy stack, a green `docker compose
ps`, and the wrong behaviour. So the standard here is not "does it run" but
**"what would have failed if this were wrong, and did I run that?"**

Four defects of exactly this shape shipped into this repo before CI existed
(a JSON-shaped list value, a wrong env var name, a missing bind-mount that the SPA
fallback hid, a LiveKit secret that differed between two files); the gates in
`scripts/` exist so they cannot come back, and each check's comment names its defect.

## Before you push

```bash
scripts/check-hygiene.sh          # dead names, JSON lists, secret and data leaks
scripts/check-links.sh            # relative markdown links resolve
scripts/check-contrast.py         # theme clears WCAG AA
scripts/check-upstream-contract.sh  # upstream still behaves as documented
```

All four run in CI on every push and pull request, and are required to merge.
`check-upstream-contract.sh` also runs weekly against upstream `main` — that
job is advisory, and a failure there means the next version bump needs a fresh
drift analysis, not that your PR is broken.

## Deploy preflight

`scripts/preflight.sh {config|stack|public}` runs on the host at deploy time —
it mechanises every silent-failure check in the runbook against the real files,
the running containers, and the live URLs. It is the difference between "the
stack is up" and "the stack is correct".

Its checks are only worth anything if they can still fail, so
`scripts/preflight-selftest.sh` builds a good fixture, breaks one thing at a
time, and asserts each break is caught. That self-test runs in CI. **If you add
a preflight check, add a mutation for it to the self-test** — an unproven check
is how the four original hollow checks got written.

## Branching

- Never commit to the default branch. Branch as `feat/`, `fix/`, `chore/` or
  `docs/`, and open a PR.
- The default branch requires all six CI checks and must be up to date before
  merge. Force-push and deletion are blocked.
- Other sessions may be working the same repo. `git fetch --prune` and check
  divergence before pushing or merging.

## Secrets

Only `*.example` files are tracked. Real values live in gitignored files:
`deploy/.env`, `deploy/env.d/common`, `deploy/env.d/postgresql`.

**Never run bare `docker compose config`.** It expands `env_file` and prints
every secret to stdout — into your scrollback, your CI log, and any session
recording. Use `--no-env-resolution` for structure, `--images` for tags.

Prefer the `*_FILE` variants for secrets where a setting supports them; see the
footer of [deploy/env.d/common.example](deploy/env.d/common.example).

## Upgrading upstream

Follow [RUNBOOK §10](RUNBOOK.md). Two things bite:

1. `docker compose restart` does **not** apply a pulled image — use `up -d`.
2. Take a `pg_dump` before `migrate`. It is the only rollback that exists.

Bump the pinned tags in `deploy/compose.override.yaml` and `UPSTREAM_REF` in
`.github/workflows/ci.yml` together — never `deploy/compose.yaml`, which is
re-fetched verbatim.
