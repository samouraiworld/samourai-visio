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
RUNBOOK.md          Step-by-step deployment. Start here.
docs/               Strategy + audit
deploy/             compose config, env templates (.example only — no secrets)
theme/custom.css    Runtime branding via FRONTEND_CSS_URL
```

## Quick orientation

- **Auth**: Clerk, as OIDC provider. Verified: `https://clerk.samourai.app/.well-known/openid-configuration`
- **Access**: `ALLOW_UNREGISTERED_ROOMS=True` — guests join by link with no account; login only to *create* a room
- **Branding**: `FRONTEND_CSS_URL` injects CSS at runtime. No fork, survives upstream upgrades
- **Not in v1**: recording, transcription, telephony

## Secrets

Never commit real secrets. Only `*.example` files are tracked; `.gitignore` blocks the rest.

Three secrets are generated at deploy time (`DB_PASSWORD`, `LIVEKIT_API_SECRET`, `DJANGO_SECRET_KEY`) and two come from the Clerk dashboard (`OIDC_RP_CLIENT_ID`, `OIDC_RP_CLIENT_SECRET`). The Clerk client secret is shown **once** and never again.

## Credit

Powered by [La Suite Meet](https://github.com/suitenumerique/meet) — MIT, by DINUM. Keep the attribution visible in the deployed UI.
