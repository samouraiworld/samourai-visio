# samourai-visio

Samouraï Visio offers free public video conferencing at
**visio.samourai.app**, powered by
[La Suite Meet](https://github.com/suitenumerique/meet).

Upstream is MIT-licensed and built by [DINUM](https://www.numerique.gouv.fr/).
This `main` branch contains deployment configuration and templates, a runtime
theme, public landing and legal pages, and validation scripts. It uses
unmodified upstream images and does not contain an application fork. The
separate `develop` branch contains application source code.

---

## Layout

```
DEPLOY.md           Operator quickstart — the linear path. Start here to deploy.
RUNBOOK.md          The detail behind each deploy step.
scripts/preflight.sh  Gates that prove each deploy stage is correct, not just up.
docs/               See docs/README.md — assessments are kept internal
deploy/             compose overrides + env templates (.example only — no secrets)
scripts/            CI gates + preflight, runnable locally
theme/custom.css    Runtime branding via FRONTEND_CUSTOM_CSS_URL
```

**Deploying?** → [DEPLOY.md](DEPLOY.md). It front-loads the inputs the owner must
supply, then walks the runbook with a preflight gate at each stage.

## Quick orientation

- **Auth**: Clerk, as OIDC provider — **off since 2026-10-07**: `clerk.samourai.app` no longer resolves. Sign-in is closed: the gateway answers the sign-in endpoints with `410 Gone`, and the backend trusts no identity provider. The theme also hides the sign-in button; that alone is not an access control. See the top of [RUNBOOK.md](RUNBOOK.md)
- **Access**: `ALLOW_UNREGISTERED_ROOMS=True` — a room materialises from any URL, so **no account is needed to create one**. What an account buys is a *persistent, owned, administrable* room. See [RUNBOOK §4 trap 1](RUNBOOK.md)
- **Branding**: `FRONTEND_CUSTOM_CSS_URL` injects CSS at runtime. No fork, survives upstream upgrades. Tokens are **Panda CSS** (`--colors-*`), not Cunningham
- **Not in v1**: recording, transcription, telephony

## Before you touch anything

Read the traps section of [RUNBOOK.md](RUNBOOK.md). Several settings in this
stack fail **silently** when misconfigured — a wrong env var name, a JSON list where a
comma-separated one is expected, or a missing bind-mount all yield a perfectly healthy
stack that does the wrong thing. The gates in `scripts/` encode those lessons; run them
locally before pushing:

```bash
scripts/check-hygiene.sh && scripts/check-upstream-contract.sh && scripts/check-contrast.py
```

## Secrets

Never commit real secrets. Only `*.example` files are tracked; `.gitignore` blocks the rest.

Three secrets are generated at deploy time (`DB_PASSWORD`, `LIVEKIT_API_SECRET`, `DJANGO_SECRET_KEY`). The two OIDC client credentials (`OIDC_RP_CLIENT_ID`, `OIDC_RP_CLIENT_SECRET`) are empty while sign-in is closed.

## Credit

Powered by [La Suite Meet](https://github.com/suitenumerique/meet) — MIT, by DINUM. Keep the attribution visible in the deployed UI.
