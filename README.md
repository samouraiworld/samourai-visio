# samourai-visio

Self-hosted [La Suite Meet](https://github.com/suitenumerique/meet) for **visio.samourai.app** — free video conferencing, open to everyone, run by Samouraï Coop.

Upstream is MIT-licensed and built by [DINUM](https://www.numerique.gouv.fr/). This repo contains **only our deployment configuration and theme** — no fork of the application.

---

## Where this sits

`samourai.app` is the Samouraï product hub, unified by a single Clerk SSO org.

| Subdomain | Product | Repo | Status |
|---|---|---|---|
| `clerk.` / `accounts.` | **Clerk auth — shared by everything** | — | live ⚠️ do not touch |
| `memba.` | Memba | `samouraiworld/memba` | live |
| `zentai.` | Zentai | `Code/Zentai` | deployed (Scaleway) |
| `visio.` | **La Suite Meet** | **this repo** | not deployed |

Related but separate:

| Path | What | Note |
|---|---|---|
| `Code/La Suite Numerique/` | 32 upstream clones | **read-only reference.** Don't put our work here |
| `Code/reportz.dev/reportz` | Contributors dashboard (Gnolove fork) | own repo, unrelated deploy |

## Layout

```
DEPLOY.md           Operator quickstart — the linear path. Start here to deploy.
RUNBOOK.md          The detail behind each deploy step.
scripts/preflight.sh  Gates that prove each deploy stage is correct, not just up.
docs/               Strategy, drift verification, plan, expert review, Clerk audit
deploy/             compose overrides + env templates (.example only — no secrets)
scripts/            CI gates + preflight, runnable locally
theme/custom.css    Runtime branding via FRONTEND_CUSTOM_CSS_URL
```

**Deploying?** → [DEPLOY.md](DEPLOY.md). It front-loads the inputs the owner must
supply, then walks the runbook with a preflight gate at each stage.

## Quick orientation

- **Auth**: Clerk, as OIDC provider. Verified: `https://clerk.samourai.app/.well-known/openid-configuration`
- **Access**: `ALLOW_UNREGISTERED_ROOMS=True` — a room materialises from any URL, so **no account is needed to create one**. What an account buys is a *persistent, owned, administrable* room. See [RUNBOOK §4 trap 1](RUNBOOK.md)
- **Branding**: `FRONTEND_CUSTOM_CSS_URL` injects CSS at runtime. No fork, survives upstream upgrades. Tokens are **Panda CSS** (`--colors-*`), not Cunningham
- **Not in v1**: recording, transcription, telephony

## Before you touch anything

Read [docs/DRIFT_REPORT_2026-07-22.md](docs/DRIFT_REPORT_2026-07-22.md) and
[docs/CTO_REVIEW_2026-07-22.md](docs/CTO_REVIEW_2026-07-22.md). Several settings in this
stack fail **silently** when misconfigured — a wrong env var name, a JSON list where a
comma-separated one is expected, or a missing bind-mount all yield a perfectly healthy
stack that does the wrong thing. The gates in `scripts/` encode those lessons; run them
locally before pushing:

```bash
scripts/check-hygiene.sh && scripts/check-upstream-contract.sh && scripts/check-contrast.py
```

## Secrets

Never commit real secrets. Only `*.example` files are tracked; `.gitignore` blocks the rest.

Three secrets are generated at deploy time (`DB_PASSWORD`, `LIVEKIT_API_SECRET`, `DJANGO_SECRET_KEY`) and two come from the Clerk dashboard (`OIDC_RP_CLIENT_ID`, `OIDC_RP_CLIENT_SECRET`). The Clerk client secret is shown **once** and never again.

## Credit

Powered by [La Suite Meet](https://github.com/suitenumerique/meet) — MIT, by DINUM. Keep the attribution visible in the deployed UI.
