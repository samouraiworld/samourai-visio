## What and why

<!-- What changes, and what problem it solves. Link the finding if there is one. -->

## Verification

<!--
Not "I ran the tests" — what did you run, and what would have failed if the
change were wrong? Several settings in this stack fail SILENTLY, so a check
that cannot fail is worse than no check.
-->

- [ ] `scripts/check-hygiene.sh`
- [ ] `scripts/check-links.sh`
- [ ] `scripts/check-contrast.py` *(if the theme changed)*
- [ ] `scripts/check-upstream-contract.sh` *(if any upstream assumption changed)*

## Silent-failure check

Tick anything this PR touches, and say how you proved it actually works:

- [ ] An **env var name** — a wrong name is ignored with no error. Proved the setting is read.
- [ ] A **list-valued setting** — comma-separated, never JSON. Proved it parses to the expected list.
- [ ] A **bind-mount or asset path** — the SPA fallback returns `200 text/html` for a missing file, never 404. Proved the content type.
- [ ] A **design token** — Panda tokens, not Cunningham. Proved the override applies to a rendered element, not just that the variable is defined.
- [ ] An **image tag** — pinned, not floating.
- [ ] Nothing above.

## Secrets

- [ ] No secret, credential, IP address or `docker compose config` output in any tracked file.

## Risk

<!-- What breaks if this is wrong, and how would you roll it back? -->
