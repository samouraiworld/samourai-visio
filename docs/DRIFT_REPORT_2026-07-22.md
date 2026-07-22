# Upstream Drift & Trap Verification — 2026-07-22

> Verification pass ordered by RUNBOOK §3 warning: *"Verified against a local clone from 2026-02-24 (5 months stale, shallow). After Step 3, diff the fetched `env.d/common` against §4 and reconcile before continuing."*
>
> **This is that reconciliation.** Everything below was re-derived from `refs/heads/main` today, not from the stale clone.

> [!IMPORTANT]
> **Corrected by expert review — see [CTO_REVIEW_2026-07-22.md](CTO_REVIEW_2026-07-22.md).** The findings below survived scrutiny (11 of 11 spot-checked line citations verified; `panda.config.ts`, `settings.py` and `theming.md` confirmed byte-identical between `main` and the pinned `v1.24.0`). Six items were wrong and are corrected here rather than silently edited:
>
> | Item | Correction |
> |---|---|
> | **Trap 1** | The *diagnosis* is right; the *fix* everyone was using is not. `["given_name","family_name"]` cannot parse — `values.ListValue` splits on `,` and never reads JSON. Use `given_name,family_name`. **This alone would have broken every display name.** |
> | **R1** | REFUTED as stated. nginx forwards inbound headers by default, so `X-Forwarded-Proto` does arrive and there is no day-one redirect loop. The real risk is the inverse: nginx-proxy's `TRUST_DOWNSTREAM_PROXY=true` lets a **client spoof** the header. Fix is `TRUST_DOWNSTREAM_PROXY=false`. |
> | **R5** | REFUTED. `mozilla_django_oidc` sends `client_secret` and `code_verifier` in the same POST unconditionally; Clerk advertises `client_secret_post` and `S256`. Keep PKCE on. The real fallbacks are `OIDC_USE_NONCE=false` then `OIDC_TOKEN_USE_BASIC_AUTH=true`. |
> | **R6** | REFUTED. Compose v2 interpolates inside `env_file`; `format: raw` is the opt-*out*. But undefined variables render as the **empty string**, not a literal `${VAR}` — so the check as written could never fire. |
> | **R12** | CONFIRMED, remediation wrong. 443/**udp** is free — nginx-proxy binds 443/**tcp** only. LiveKit TURN on UDP/443 is available today at zero cost; no second IP needed. |
> | **Token table** | `--colors-error` is not a semantic token. `panda.config.ts:171` defines an `error` *palette ramp*; the semantic destructive token at `:316` is `--colors-danger`. Inherited from an error in upstream's own `theming.md:57`. |

## Method

All artefacts re-fetched 2026-07-22, all HTTP 200, all from `suitenumerique/meet@main` unless noted:

| Artefact | Path |
|---|---|
| Compose example | `docs/examples/compose/compose.yaml` |
| Env templates | `env.d/production.dist/{hosts,common,postgresql}` |
| LiveKit example | `docs/examples/livekit/server.yaml` |
| Inner nginx | `docker/files/production/default.conf.template` |
| **Settings (authority)** | `src/backend/meet/settings.py` (1369 lines) |
| URL mounting | `src/backend/core/urls.py` |
| Flag semantics | `src/backend/core/api/viewsets.py` |
| **Design tokens (authority)** | `src/frontend/panda.config.ts` (424 lines) |
| Theming docs | `docs/theming.md` |
| OIDC routes | `suitenumerique/django-lasuite@main` → `src/lasuite/oidc_login/urls.py` |
| Logout behaviour | `suitenumerique/django-lasuite@main` → `src/lasuite/oidc_login/views.py` |
| Callback route | `mozilla/mozilla-django-oidc@main` → `mozilla_django_oidc/urls.py` |

Stale local reference for comparison: `Code/La Suite Numerique/apps/meet` @ `d76b4c9` (2026-02-24, shallow).

---

## Part 1 — Env template drift

Key-by-key diff, upstream `env.d/production.dist/common` vs `deploy/env.d/common.example`.

### Verdict: the template itself has **not** drifted structurally

Every key present in the Feb-2026-derived analysis is still present upstream with the same shape. No new required keys appeared. No keys were removed or renamed. **The §4 config block is still built on a valid base.**

### Keys upstream has that we omit — 1, deliberate

| Key | Why omitted |
|---|---|
| `OIDC_OP_LOGOUT_ENDPOINT` | Clerk advertises no logout endpoint. See Trap 3. ⚠️ Upstream **sets** this to a Keycloak URL at line 33 — it must not survive a copy-paste. |

### Keys we add that upstream doesn't ship — 8, of which **7 valid and 1 invalid**

| Key | In `settings.py`? | |
|---|---|---|
| `DJANGO_EMAIL_USE_TLS` | `:430` (`EMAIL_USE_TLS`, `DJANGO_` prefix) | ✅ |
| `OIDC_CREATE_USER` | `:479-481` | ✅ |
| `OIDC_USE_PKCE` | `:536-538` | ✅ |
| `OIDC_PKCE_CODE_CHALLENGE_METHOD` | `:539-543` | ✅ |
| `OIDC_REDIRECT_REQUIRE_HTTPS` | `:559-561` | ✅ |
| `OIDC_USERINFO_FULLNAME_FIELDS` | `:574-578` | ✅ |
| `OIDC_USERINFO_SHORTNAME_FIELD` | `:579-583` | ✅ |
| **`FRONTEND_CSS_URL`** | **absent — no such setting** | ❌ **BLOCKER-1** |

### Values that differ where both ship the key — all intended

`ALLOW_UNREGISTERED_ROOMS` (False→True), `OIDC_RP_SCOPES` (`"openid email"`→`"openid email profile"`), the four `OIDC_OP_*` endpoints (Keycloak→Clerk), and the mail/branding block. All reviewed, all correct.

---

## Part 2 — Blocking defects

### BLOCKER-1 · `FRONTEND_CSS_URL` is not a real setting — the theme never loads

The variable does not exist. The real name is **`FRONTEND_CUSTOM_CSS_URL`**:

```python
# settings.py:375-380
FRONTEND_CONFIGURATION = {
    # If set, a <link> tag with this URL as href is added to the <head> of the frontend app.
    "custom_css_url": values.Value(
        None, environ_name="FRONTEND_CUSTOM_CSS_URL", environ_prefix=None
    ),
```

Corroborated by `docs/theming.md`: *"simply set the `FRONTEND_CUSTOM_CSS_URL` environment variable (of the **backend** service)"*.

**Why this is nasty:** Django silently ignores unrecognised env vars. There is no warning, no startup error, no log line. The stack comes up perfectly healthy and the branding is simply absent — and the natural next move is to go debugging CSS that was never requested.

**Affected:** `deploy/env.d/common.example:67`, `RUNBOOK.md:207`.

### BLOCKER-2 · `theme/custom.css` targets a design system Meet no longer uses

`theme/custom.css` is written against **Cunningham** (`--c--theme--colors--*`). Upstream migrated the frontend to **Panda CSS**. The authority is now `src/frontend/panda.config.ts`.

Not one declaration in the current file matches a live token. **The effective yield of the theme file is zero**, independently of BLOCKER-1.

Real token names, from `panda.config.ts` + `theming.md`:

| Purpose | Real token | Our (dead) token |
|---|---|---|
| Brand / buttons / links | `--colors-primary` | `--c--theme--colors--primary-500` |
| Primary hover / active | `--colors-primary-hover`, `--colors-primary-active` | — |
| In-room (dark) primary | `--colors-primary-dark-500` *(50–950 + `action`)* | — |
| Greyscale ramp | `--colors-greyscale-000` … `--colors-greyscale-1000` | `--c--theme--colors--greyscale-1000` |
| Destructive / success / warning / alert | `--colors-danger`, `--colors-success`, `--colors-warning`, `--colors-alert` *(`--colors-error` is a palette ramp `-100…950`, not a semantic token — `theming.md:57` is wrong)* | — |
| Fonts | `--fonts-sans`, `--fonts-serif`, `--fonts-mono` | `--c--theme--font--families--base` |

> ⚠️ **Near-miss trap.** Panda also defines `greyscale-1000`. The *leaf* name matches ours exactly; only the prefix differs. Anyone eyeballing the diff will read `greyscale-1000` in both columns and conclude the file is fine.

**Second structural error.** `theming.md` states: *"The app does **not provide separate light/dark themes**: outside a meeting it defaults to light, and in a room it switches to dark."* Our file declares one `:root` block setting a dark background (`#141416`). The correct model is a light surface outside the room driven by `primary`/`greyscale`, and a dark surface inside driven by the separate `primaryDark` ramp. The current file encodes the wrong mental model, not merely the wrong names.

### BLOCKER-3 · `/custom/style.css` has no server behind it

`FRONTEND_CUSTOM_CSS_URL=/custom/style.css` resolves to `https://visio.samourai.app/custom/style.css`. Nothing serves that path.

`theming.md` gives the mechanism — bind-mount over the frontend container's web root:

```
/usr/share/nginx/html/assets      ← documented asset override path
```

The upstream `compose.yaml` `frontend` service mounts only `./default.conf.template`. Without an added mount, the CSS 404s — and so does `DJANGO_EMAIL_LOGO_IMG="https://${MEET_HOST}/custom/logo.png"`, which means every invitation email ships a broken image.

**Three independent faults, all on the same feature.** Each alone is sufficient to make branding silently absent. Fixing any one or two of them changes nothing observable.

---

## Part 3 — The four traps, verified against current source

### Trap 1 · `OIDC_USERINFO_FULLNAME_FIELDS` — ✅ CONFIRMED (line moved)

```python
# settings.py:574-578   (RUNBOOK cites :505 — line drifted, claim still true)
OIDC_USERINFO_FULLNAME_FIELDS = values.ListValue(
    default=["given_name", "usual_name"], ...
)
```

`usual_name` is ProConnect-specific and absent from Clerk's `claims_supported`. Override to `["given_name","family_name"]` is required and correct.

### Trap 2 · `OIDC_RP_SCOPES` — ✅ CONFIRMED (line moved)

```python
# settings.py:533-535   (RUNBOOK cites :464 — line drifted, claim still true)
OIDC_RP_SCOPES = values.Value("openid email", ...)
```

Upstream's env template ships the same narrow value. `"openid email profile"` is required and correct.

### Trap 3 · No logout endpoint — ✅ CONFIRMED, and proven safe in source

Default is `None` (`settings.py:526-528`), so leaving it unset is legal. More importantly, the behaviour is **graceful, not merely tolerated**:

```python
# django-lasuite src/lasuite/oidc_login/views.py:89-92
oidc_logout_endpoint = self.get_settings("OIDC_OP_LOGOUT_ENDPOINT")
if not oidc_logout_endpoint:
    return self.redirect_url
# :127-128 — post() then reaches:
if logout_url == self.redirect_url:
    auth.logout(request)
```

Falsy endpoint → return the plain redirect URL → `auth.logout()` runs → user lands on `LOGOUT_REDIRECT_URL`. No exception, no 500. The RUNBOOK's stated consequence — Django session cleared, Clerk SSO session retained, so log-out-then-log-in silently re-authenticates — is **exactly right**.

### Trap 4 · `ALLOW_UNREGISTERED_ROOMS` — ✅ CONFIRMED, with two corrections

**Correction A — the repo's two claims are both true and read as contradictory.**

| Source | Claim | Status |
|---|---|---|
| `docs/PLAN_2026-07-22.md:40` | `True` is the default (`settings.py:596`) | ✅ true of the **code** — now `:665-666` |
| `RUNBOOK.md:34` | the production template ships `False` | ✅ true of the **env template** — `common:50` |

Both are correct about different layers, and **the env file wins**. Nothing is wrong except that a reader hits one, then the other, and cannot tell which to trust. It should be stated explicitly.

**Correction B — the §8 smoke test does not test this flag.** The flag has exactly one use site:

```python
# core/api/viewsets.py:257-277  — RoomViewSet.retrieve
try:
    instance = self.get_object()
except Http404:
    if not settings.ALLOW_UNREGISTERED_ROOMS:
        raise
    slug = slugify(self.kwargs["pk"])
    data = {"id": None, "slug": slug, "is_administrable": False,
            "access_level": RoomAccessLevel.PUBLIC,
            "livekit": {...token...}}
```

It fires **only on `Http404`** — a slug that is *not in the database*. It grants ad-hoc rooms conjured from a URL.

RUNBOOK §8 says:

> - [ ] Create a room as a logged-in user
> - [ ] **Open the room link in a private window — joins with no account** *(validates `ALLOW_UNREGISTERED_ROOMS`)*

A room created by a logged-in user **is** in the database. `get_object()` succeeds, `Http404` never raises, and the flag is never consulted. That test exercises `RoomPermissions` and the room's `access_level` — a different code path that would behave identically with the flag set to `False`.

**Both tests are needed, and they are different tests.** To validate the flag you must open a slug that was never created — e.g. `https://visio.samourai.app/zzz-test-unregistered-2026`. Corrected in the implementation plan.

---

## Part 4 — Risks found that the RUNBOOK does not cover

| # | Sev | Finding |
|---|---|---|
| **R1** | High | **`X-Forwarded-Proto` is never set by the inner nginx.** Production sets `SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")` (`:1291`) and `SECURE_SSL_REDIRECT=True` (`:1295`). `default.conf.template` sets only `Host` and `X-Forwarded-For`. The chain depends on the outer nginx-proxy injecting the header *and* the inner nginx passing it through untouched. If it doesn't arrive: infinite redirect loop, and OIDC builds `http://` redirect URIs that Clerk will reject. Must be tested explicitly, not assumed. |
| **R2** | High | **Sessions live in an unpersisted Redis.** `SESSION_ENGINE=…backends.cache` (`:466`) → `SESSION_CACHE_ALIAS="default"` → `redis://redis:6379/1`. The compose `redis:` service has **no volume**. Every Redis restart logs out every user mid-call. Compounded by `redis:5`, years past EOL. |
| **R3** | Med | **`CSRF_TRUSTED_ORIGINS` is empty in Production** (`:1278`). Same-origin POSTs should pass on host comparison, but this is the classic source of 403-on-login-POST behind a TLS-terminating proxy. Keep the one-line fix staged. |
| **R4** | Med | **LiveKit scheme.** We pass `LIVEKIT_API_URL=https://…`; browsers need `wss://`. `LIVEKIT_FORCE_WSS_PROTOCOL` exists (`:637-639`, default `False`) as the escape hatch. Unverified either way. |
| **R5** | Med | **PKCE + confidential client, untested against Clerk.** We enable `OIDC_USE_PKCE=true` (upstream default `False`) *while* sending a client secret. Clerk advertises `S256`. Legal per spec and supported by mozilla-django-oidc, but this exact pairing is unproven here. `false` is the instant fallback. |
| **R6** | Med | **`${VAR}` interpolation inside `env_file` is version-dependent.** Upstream's own template puts `${MEET_HOST}` inside `env.d/common`, which is loaded via `env_file:` — where Compose's substitution semantics have changed across versions. If it does not interpolate, `DJANGO_ALLOWED_HOSTS` becomes the literal string `${MEET_HOST}` and **every request 400s**. One command settles it; do not assume. |
| **R7** | Med | **Everything is on `latest`** — `meet-backend`, `meet-frontend`, `livekit-server`. Released tags available today: **`lasuite/meet-backend:v1.24.0`**, **`lasuite/meet-frontend:v1.24.0`** (both 2026-07-21), **`livekit/livekit-server:v1.13.4`** (2026-07-18). Also `postgres:16`, `redis:5`. |
| **R8** | Med | **Use file-based secrets.** `SECRET_KEY`, `OIDC_RP_CLIENT_SECRET`, `EMAIL_HOST_PASSWORD`, `LIVEKIT_API_KEY`/`_SECRET` are all `SecretFileValue` (`lasuite.configuration.values`), so they support a file variant instead of plaintext in env. Strictly better than the runbook's approach. |
| **R9** | Low | **`OIDC_STORE_ID_TOKEN=True`** by default (`:565-567`) → Clerk ID tokens sit in the Redis-backed session. Harmless operationally; it is PII in a cache and belongs in the retention policy. |
| **R10** | Policy | **Shared-org blast radius.** Every existing `*.samourai.app` Clerk account can create rooms on day one, and every Visio signup becomes a Samouraï account everywhere. The RUNBOOK flags this; it needs an explicit go/no-go and a CGU clause, not just a note. |
| **R11** | Perf | **LiveKit runs on a single UDP port** (`udp_port: 7882`). Upstream's own comment recommends a port *range* ≥ vCPU count. `port_range_start/end` and `udp_port` are **mutually exclusive**, and a range needs firewall changes that are not in the currently-open set. |
| **R12** | High | **There is no TURN server.** RUNBOOK §2 opens `443/udp` "TURN/TLS" and §8 asserts a restrictive-network call "proves TURN over 443 works" — but the upstream `livekit-server.yaml` contains **no `turn:` block at all**. Nothing listens on 443/udp. Worse, TURN/TLS wants 443/tcp, which nginx-proxy already owns. Users behind corporate firewalls will simply fail to connect, and the smoke test as written cannot pass. This needs an architectural decision before launch, not a checkbox. |

---

## Summary

| Item | Result |
|---|---|
| Env template drift since Feb 2026 | **None structural.** The §4 base is still valid. |
| Config traps 1–4 | **All four confirmed.** Two line-number citations stale; both claims still true. |
| Trap 4 smoke test | **Mis-specified** — tests the wrong code path. Corrected. |
| Trap 4 documentation | **Two true statements that read as contradictory.** Needs one sentence. |
| Branding | **Three independent blockers.** Currently 0% functional. |
| New risks | **12**, of which 3 High (R1, R2, R12). |

The analysis inherited from the stale clone held up well: the traps were real, correctly diagnosed, and correctly fixed. What the stale clone could not show was the **frontend migration off Cunningham** — and that is precisely where the damage is concentrated.
