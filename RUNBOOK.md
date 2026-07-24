# Runbook — visio.samourai.app

> La Suite Meet, self-hosted on Scaleway, authenticated against the existing **Clerk** org (`clerk.samourai.app`).
> Written 2026-07-22. Execute top to bottom.

> [!WARNING]
> **Verified against the local clone of `suitenumerique/meet`, which is from 2026-02-24 (5 months stale, shallow).**
> The `curl` commands in Step 3 pull **current** upstream config, which may have drifted from the analysis here.
> After Step 3, diff the fetched `env.d/common` against §4 and reconcile before continuing.

---

## 0. What you're deploying

| Service | Role |
|---|---|
| PostgreSQL | Main database |
| Redis | Cache + inter-service |
| LiveKit | WebRTC SFU — the bandwidth cost driver |
| Meet backend (Django) | API, rooms, auth |
| Meet frontend | React app |
| Reverse proxy | TLS termination (nginx-proxy + Let's Encrypt, or Caddy) |
| **Clerk** (external) | OIDC identity provider — already running |

**Not in v1:** recording, transcription, summarisation, telephony. Each needs MinIO, `livekit-egress`, and dedicated Celery workers.

### Access model

**Product requirement: Visio must be usable without an account, like Google Meet.** Verified against `v1.24.0` — this already works, and is *more* open than Google Meet.

| Who | What they can do | What they need |
|---|---|---|
| Anonymous visitor | **Join** any room by link | Nothing — they type a display name on the join screen |
| Anonymous visitor | **Create** a room from any URL | Nothing (`ALLOW_UNREGISTERED_ROOMS=True`) |
| Signed-in user | Own an **administrable, persistent** room | Clerk login |

How the guest path works, end to end:

1. Visitor opens `https://visio.samourai.app/<any-slug>`.
2. The backend can't find the slug, raises `Http404`, and — because the flag is on — returns a synthetic public room plus a LiveKit token (`core/api/viewsets.py:257-277`).
3. The join screen renders a **required** name field for anyone not signed in, and passes it as `?username=` (`Join.tsx:457-465`). The browser remembers it.

> Google Meet requires an account to *create* a meeting. Here an anonymous visitor can conjure a working room from any URL. The trade: those rooms have no owner, no admin controls (`is_administrable: false`), and no attribution — which is the same fact that makes abuse reports unactionable. Decide that deliberately.

Two settings interact with this and should be tested before launch:

- **`FRONTEND_IS_SILENT_LOGIN_ENABLED`** (default `true`) redirects every anonymous visitor to Clerk with `prompt=none`, rate-limited via `localStorage`. Keeping it on means returning signed-in users are recognised without clicking "log in"; turning it off removes a redirect from every guest's first visit. The callback only handles `error=login_required` gracefully — test the anonymous path.
- **`AUTHENTICATED_PARTICIPANTS_CAN_EDIT_DISPLAY_NAME`** (default `true`) shows the same name field to signed-in users, pre-filled from `full_name`.

Session: Django cookie, 12 h.

> [!IMPORTANT]
> The production template ships `ALLOW_UNREGISTERED_ROOMS=False`. For a free public instance you **must** flip it to `True` (§4). This is the single most consequential line in the config.

---

## 1. Clerk — create the OAuth application

Your instance is **already a working OIDC provider**. Verified live:

```
https://clerk.samourai.app/.well-known/openid-configuration → HTTP 200
```

```
issuer                  https://clerk.samourai.app
authorization_endpoint  https://clerk.samourai.app/oauth/authorize
token_endpoint          https://clerk.samourai.app/oauth/token
userinfo_endpoint       https://clerk.samourai.app/oauth/userinfo
jwks_uri                https://clerk.samourai.app/.well-known/jwks.json
scopes_supported        offline_access, user:org:read, email, profile,
                        public_metadata, private_metadata, openid
claims_supported        email, email_verified, given_name, family_name, name,
                        sub, iat, preferred_username, picture, aud, iss, exp, org_id
code_challenge_methods  S256                    ← PKCE available
id_token_signing_alg    RS256                   ← matches OIDC_RP_SIGN_ALGO
backchannel_logout      false
frontchannel_logout     false                   ← no logout endpoint (see §4 note)
```

**Steps** (Clerk Dashboard → *OAuth applications* → *Add OAuth application*):

1. Name: `Visio Samouraï`
2. Scopes: **`openid`, `email`, `profile`** — `profile` is required or user names arrive empty

> [!WARNING]
> **The `profile` scope is necessary but not sufficient, and on this instance it is currently not enough.**
> Audited 2026-07-22: `first_name` and `last_name` are **disabled** on `clerk.samourai.app`, so the sign-up form collects no name, `userinfo` carries no `given_name`/`family_name`, and `full_name` is `NULL` for every user — regardless of scopes or env vars.
> Re-check with `scripts/audit-clerk-instance.sh`. Options, tradeoffs and a recommendation: [docs/CLERK_INSTANCE_AUDIT_2026-07-22.md](docs/CLERK_INSTANCE_AUDIT_2026-07-22.md).
> Enabling those attributes changes the sign-up form for **Memba and Zentai** as well — this instance is shared.
3. Redirect URI — exactly:
   ```
   https://visio.samourai.app/api/v1.0/callback/
   ```
   *(Meet mounts `lasuite.oidc_login.urls` under `api/{API_VERSION}/` in `core/urls.py:37-45`; `API_VERSION = "v1.0"`.)*
4. Copy the **Client Secret immediately** — Clerk does not store it and will never show it again
5. Copy the **Client ID** from the app settings page

> [!NOTE]
> Because this reuses the shared org, **every existing Samouraï account (Memba, Zentai, …) can create rooms on day one**, and every new Visio signup becomes a Samouraï account everywhere. That's the intent — just be deliberate about it, and make sure your CGU covers it.

---

## 2. Server + DNS

### Sizing

LiveKit SFU is **CPU- and bandwidth-bound**, and load scales with *participant-minutes*, not signups.

- Start: **4–8 vCPU, 16–32 GB RAM**
- ⚠️ **Check the instance's network bandwidth cap before ordering** — on Scaleway this varies sharply by instance type and it, not CPU, is what will bite you first
- Measure at 10 / 50 / 200 concurrent participants before promoting publicly

### DNS (A records → instance IP)

| Host | Purpose |
|---|---|
| `visio.samourai.app` | Meet frontend + backend |
| `livekit.samourai.app` | LiveKit SFU |

No `id.` record needed — Clerk replaces Keycloak.

### Firewall

```bash
ufw allow 80/tcp              # TLS issuance
ufw allow 443/tcp             # HTTPS (nginx-proxy)
ufw allow 443/udp             # TURN over UDP
ufw allow 7881/tcp            # WebRTC ICE over TCP
ufw allow 7882/udp            # WebRTC multiplexing over UDP
ufw allow 30000:30100/udp     # TURN relay allocations
ufw enable
```

> [!IMPORTANT]
> **Two things this does not do.**
>
> **1. ufw does not govern container exposure.** Docker publishes ports via the `DOCKER-USER` iptables chain, *before* ufw sees the packet — so a published port is open with or without a `ufw allow`, and a `ufw deny` will not close it. These rules are documentation, not enforcement. What actually determines exposure is `ports:` in compose. The live risk is a future debugging `"5432:5432"`, which would publish PostgreSQL to the internet regardless of ufw; bind debug ports to `127.0.0.1:5432:5432`.
>
> **2. The Scaleway security group is a second, independent filter** that `ufw status` cannot see. A green ufw check with a closed security group is the most common cause of "signalling works, no media". Verify both.

Confirm what is genuinely exposed:

```bash
docker compose ps --format '{{.Service}}\t{{.Ports}}'
```

---

## 3. Fetch upstream config

```bash
mkdir -p ~/visio/env.d && cd ~/visio
curl -o compose.yaml https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/docs/examples/compose/compose.yaml
curl -o .env https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/env.d/production.dist/hosts
curl -o env.d/common https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/env.d/production.dist/common
curl -o env.d/postgresql https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/env.d/production.dist/postgresql
curl -o livekit-server.yaml https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/docs/examples/livekit/server.yaml
curl -o default.conf.template https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/docker/files/production/default.conf.template
```

Generate three secrets:

```bash
openssl rand -base64 48                # DB_PASSWORD        (64 chars — one line)
openssl rand -base64 48                # LIVEKIT_API_SECRET (64 chars — one line)
openssl rand -base64 64 | tr -d '\n'   # DJANGO_SECRET_KEY  (88 chars — WRAPS)
```

> [!WARNING]
> `openssl rand -base64 64` wraps at 64 columns and emits **two lines**. Pasted into an env file, `DJANGO_SECRET_KEY` is truncated at the wrap and the remainder becomes a junk variable — with no error. The `tr -d '\n'` is not optional. `-base64 48` produces exactly 64 characters and does not wrap, which is why only the third command needs it.

> [!NOTE]
> The fetched `default.conf.template` is **reference material only** since the
> gateway override: `compose.override.yaml` mounts the repo's
> [`deploy/nginx/default.conf.template`](deploy/nginx/default.conf.template)
> at the same target, which is upstream's file plus 301s for the SPA's
> hardcoded DINUM legal routes (§7bis). Keep fetching it — it is what you
> diff against when the upstream-contract gate flags gateway drift (§10).
> Copy the repo's `deploy/nginx/` to `~/visio/nginx/` alongside `landing/`.

Then assert every line is a well-formed `KEY=value`:

```bash
awk -F= 'NF<2 || $1 ~ /[^A-Z0-9_]/ {print NR": "$0}' env.d/common
```

Expected: no output.

---

## 4. Configure

### `.env`

```env
MEET_HOST=visio.samourai.app
LIVEKIT_HOST=livekit.samourai.app
BACKEND_INTERNAL_HOST=backend
FRONTEND_INTERNAL_HOST=frontend
LIVEKIT_INTERNAL_HOST=livekit
# KEYCLOAK_HOST / REALM_NAME are unused — Clerk replaces Keycloak
```

### `env.d/postgresql`

Set `DB_PASSWORD` to the generated value. Leave the rest.

### `env.d/common` — the Clerk-specific version

Replace the whole OIDC block from the Keycloak template with this:

```env
# ── Django ──
DJANGO_ALLOWED_HOSTS=${MEET_HOST}
DJANGO_SECRET_KEY=<generated>
DJANGO_SETTINGS_MODULE=meet.settings
DJANGO_CONFIGURATION=Production
PYTHONPATH=/app
MEET_BASE_URL="https://${MEET_HOST}"
# BACKEND default locale (settings.py:217). Sets the default User.language and
# the last-resort e-mail fallback. It does NOT set the SPA's interface language
# — that is resolved client-side by i18next from the visitor's browser.
DJANGO_LANGUAGE_CODE=fr-fr

# ── Mail — Scaleway Transactional Email (French, EU) ──
# Username = Project ID that owns the TEM domain; password = an API key's
# secret key (with TEM rights). Verify the sending domain in TEM first.
DJANGO_EMAIL_HOST=smtp.tem.scaleway.com
DJANGO_EMAIL_HOST_USER=<Scaleway Project ID>
DJANGO_EMAIL_HOST_PASSWORD=<Scaleway API secret key>
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_USE_TLS=true
DJANGO_EMAIL_FROM=visio@samourai.app
DJANGO_EMAIL_BRAND_NAME="Samouraï Visio"
DJANGO_EMAIL_LOGO_IMG="https://${MEET_HOST}/custom/logo.png"

# ── OIDC — Clerk ──
OIDC_OP_JWKS_ENDPOINT=https://clerk.samourai.app/.well-known/jwks.json
OIDC_OP_AUTHORIZATION_ENDPOINT=https://clerk.samourai.app/oauth/authorize
OIDC_OP_TOKEN_ENDPOINT=https://clerk.samourai.app/oauth/token
OIDC_OP_USER_ENDPOINT=https://clerk.samourai.app/oauth/userinfo
# OIDC_OP_LOGOUT_ENDPOINT deliberately unset — Clerk advertises no logout endpoint

OIDC_RP_CLIENT_ID=<from Clerk>
OIDC_RP_CLIENT_SECRET=<from Clerk>
OIDC_RP_SIGN_ALGO=RS256
OIDC_RP_SCOPES="openid email profile"

# Comma-separated. NOT JSON — see trap 2.
# preferred_username, because this Clerk instance collects no first/last name
# (see the Clerk audit). Requires `username` enabled in Clerk. See trap 3.
OIDC_USERINFO_FULLNAME_FIELDS=preferred_username
OIDC_USERINFO_SHORTNAME_FIELD=preferred_username
OIDC_USERINFO_ESSENTIAL_CLAIMS=email

OIDC_USE_PKCE=true
OIDC_PKCE_CODE_CHALLENGE_METHOD=S256
OIDC_CREATE_USER=true
OIDC_REDIRECT_REQUIRE_HTTPS=true
# Host only — no scheme, no brackets.
OIDC_REDIRECT_ALLOWED_HOSTS=${MEET_HOST}
OIDC_STORE_ID_TOKEN=false

LOGIN_REDIRECT_URL=https://${MEET_HOST}
LOGIN_REDIRECT_URL_FAILURE=https://${MEET_HOST}
LOGOUT_REDIRECT_URL=https://${MEET_HOST}

# ── LiveKit ──
LIVEKIT_API_SECRET=<generated>
LIVEKIT_API_KEY=meet
LIVEKIT_API_URL=https://${LIVEKIT_HOST}
LIVEKIT_FORCE_WSS_PROTOCOL=true

# ── Public instance ──
ALLOW_UNREGISTERED_ROOMS=True

# ── Branding ──
FRONTEND_CUSTOM_CSS_URL=/custom/style.css
```

### Five config traps

**1. `ALLOW_UNREGISTERED_ROOMS` — two true statements that look contradictory.**
The **code** default is `True` (`settings.py:665`). The **production env template** ships `False` (`env.d/production.dist/common:50`). Both are correct; the env file wins, so a stock deploy requires an account merely to *join* a call. Set `True`.

What it actually does (`core/api/viewsets.py:257-277`): it fires **only** when `RoomViewSet.retrieve` raises `Http404` — a slug **not in the database** — and then returns a synthetic public room plus a LiveKit token. It grants *ad-hoc rooms conjured from a URL*, and has no effect on rooms that already exist. Consequence for the product: **an account is not required to create a working room**, only to own an administrable one.

**2. List settings are comma-separated, not JSON.**
`values.ListValue` parses with `value.strip().split(',')` (`django-configurations configurations/values.py:238`) and never reads JSON. `["given_name","family_name"]` becomes `['["given_name"', '"family_name"]']`, so `user_info.get(...)` returns `None` and **every display name is empty**. There is no error. Upstream's own template gets this wrong at `env.d/production.dist/common:44`. Affects `OIDC_USERINFO_FULLNAME_FIELDS`, `OIDC_REDIRECT_ALLOWED_HOSTS`, `OIDC_USERINFO_ESSENTIAL_CLAIMS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.

**3. `OIDC_USERINFO_FULLNAME_FIELDS` — override the default, and match it to what the instance actually collects.**
Meet defaults to `["given_name", "usual_name"]` (`settings.py:574`). `usual_name` is a **ProConnect-specific** claim Clerk never emits, so the default leaves every display name empty. We set **`preferred_username`** — because the Clerk instance has first/last name **disabled** (verified: [docs/CLERK_INSTANCE_AUDIT_2026-07-22.md](docs/CLERK_INSTANCE_AUDIT_2026-07-22.md)), so a public username handle is the only name field that actually arrives. This **requires enabling `username` in the Clerk dashboard**. (A single token also can't be mis-split by trap 2.)

**4. `OIDC_RP_SCOPES` — the default is too narrow.**
Default is `"openid email"` (`settings.py:533`). Without `profile` you get no profile claims — including `preferred_username` — and names render empty regardless of trap 3. The scope is necessary but **not sufficient**: Clerk emits `preferred_username` only if the instance has **`username` enabled**, a setting shared with every other `*.samourai.app` product.

**5. No logout endpoint.**
Clerk reports `backchannel_logout_supported: false` and `frontchannel_logout_supported: false`. Leave `OIDC_OP_LOGOUT_ENDPOINT` unset. Consequence: signing out of Meet clears the local Django session but **not** the Clerk SSO session — clicking "log out" then "log in" silently re-authenticates. Acceptable for a shared-SSO product; surprising if you don't expect it. If you need true logout, redirect to Clerk's sign-out URL after `LOGOUT_REDIRECT_URL`.

### `livekit-server.yaml`

Copy [`deploy/livekit-server.yaml.example`](deploy/livekit-server.yaml.example) — it is the upstream example plus a `turn:` block, which upstream omits entirely.

Set the same `LIVEKIT_API_SECRET` against key `meet`, then **assert it matches**:

```bash
A=$(grep -E '^\s+meet:' livekit-server.yaml | sed 's/.*meet:[[:space:]]*//' | tr -d '"'"'"' ')
B=$(grep '^LIVEKIT_API_SECRET=' env.d/common | cut -d= -f2- | tr -d '"'"'"' ')
[ -n "$A" ] && [ "$A" = "$B" ] && echo MATCH || echo "MISMATCH — nobody will be able to join a room"
```

A mismatch is invisible: the stack comes up healthy, TLS works, `https://livekit.samourai.app` returns 200 — and every token the backend mints fails signature validation.

The example multiplexes WebRTC on a **single UDP port**. A **port range** performs materially better under load, but `udp_port` and `port_range_start/end` are mutually exclusive and a range widens the firewall — leave it until a measurement justifies the change.

### Configure via `compose.override.yaml`, not `compose.yaml`

All our deltas — pinned tags, restart policies, the Redis volume, the CSS mount, the TURN ports, the proxy wiring — live in [`deploy/compose.override.yaml`](deploy/compose.override.yaml), which Compose loads automatically alongside `compose.yaml`.

**Do not edit `compose.yaml`.** §10 re-fetches it verbatim on every upgrade and would silently discard those edits. Upstream ships `latest` on every service; the override pins them.

---

## 5. Reverse proxy + TLS

Use the upstream [nginx-proxy example](https://github.com/suitenumerique/meet/tree/main/docs/examples/compose/nginx-proxy) (auto Let's Encrypt), in its **own** compose project. The `VIRTUAL_HOST` / `LETSENCRYPT_HOST` wiring is already in [`deploy/compose.override.yaml`](deploy/compose.override.yaml) — nothing to uncomment.

```bash
docker network create proxy-tier
```

Two edits to the nginx-proxy example are mandatory:

```yaml
    environment:
      # Cert-expiry warnings go here. The upstream example ships
      # mail@yourdomain.tld, and a bogus ACME contact means no warning.
      - DEFAULT_EMAIL=<a monitored coop address>

      # nginx-proxy forwards a CLIENT-supplied X-Forwarded-Proto unchanged by
      # default. Meet's Production settings trust that header
      # (SECURE_PROXY_SSL_HEADER), so with the default any client can send
      # `X-Forwarded-Proto: https` over plaintext port 80 and Django treats the
      # request as secure — defeating SECURE_SSL_REDIRECT and making
      # request.is_secure() attacker-controlled. There is no downstream proxy
      # in this architecture, so this must be false.
      - TRUST_DOWNSTREAM_PROXY=false

      # FIRST RUN ONLY — prove issuance against staging before spending the
      # Let's Encrypt budget. samourai.app is shared with clerk/memba/zentai,
      # and the limits (5 failed validations/hostname/hour, 50 certs/domain/
      # week) are per registered domain.
      - ACME_CA_URI=https://acme-staging-v02.api.letsencrypt.org/directory
```

Watch `docker compose logs -f acme-companion` until both certificates issue against staging, then remove `ACME_CA_URI`, recreate, and confirm real issuance.

> **If issuance fails:** check for stray `AAAA` records (Let's Encrypt will validate over IPv6 and fail) and `CAA` records that do not name `letsencrypt.org`, confirm port 80 is reachable from the public internet, and read the acme-companion log. Do not loop `up -d` — you will burn the rate limit.

Back up the nginx-proxy `certs` and `acme` volumes. They live in a *different* compose project, so a `down -v` there destroys the ACME account key and every certificate.

Caddy alternative: expose `frontend` on `8086:8086` and proxy to it.

---

## 6. Launch

> [!TIP]
> **Run the preflight at each stage — it mechanises every silent-failure check in this runbook.**
>
> ```bash
> cd ~/visio
> VISIO_DIR=~/visio /path/to/repo/scripts/preflight.sh config   # before `up` — files on disk
> VISIO_DIR=~/visio /path/to/repo/scripts/preflight.sh stack    # after `up`  — resolved settings
> VISIO_DIR=~/visio /path/to/repo/scripts/preflight.sh public   # after TLS   — the live surface
> ```
>
> It fails on: unfilled placeholders, a wrapped secret, JSON-shaped lists, a LiveKit-secret mismatch, the wrong CSS variable, a missing bind-mount (checking content-type, not status, because the SPA fallback returns 200 for a missing file), a floating image tag, an unresolved `${VAR}`, a spoofable `X-Forwarded-Proto`, a guest-join path that does not actually work, and a log-retention setup that does not match what the privacy policy publishes (§8bis). It prints `SKIP` for the handful of things a script cannot prove — UDP reachability, the Scaleway security group, `prompt=none` — and each SKIP explains why. **A SKIP is not a pass.**

```bash
docker compose up -d
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py createsuperuser --email <admin@samourai.app>
```

Admin at `https://visio.samourai.app/admin`.

---

## 7. Branding

`FRONTEND_CUSTOM_CSS_URL` — a **backend** setting — injects CSS at runtime via a `<link>` in `<head>`: **no rebuild, no fork, survives upgrades**. The theme lives in [`theme/custom.css`](theme/custom.css); copy it to `deploy/custom/style.css`, which `compose.override.yaml` bind-mounts into the frontend web root.

> [!WARNING]
> The variable is `FRONTEND_CUSTOM_CSS_URL`. `FRONTEND_CSS_URL` **does not exist**, and Django ignores unknown env vars silently — a wrong name gives a perfectly healthy stack with no theme and no error anywhere.

**Tokens are [Panda CSS](https://panda-css.com/), not Cunningham.** Meet migrated the frontend, so every `--c--theme--*` name is dead and fails silently. The authority is `src/frontend/panda.config.ts`. Override the **palette ramp** (`--colors-primary-800`, `--colors-primary-dark-100`), not only the semantic tier — `buttonRecipe.ts:56` paints the primary button from `primary.800` with a literal `white`, so overriding `--colors-primary` alone leaves every button Bleu France.

Meet has **no light/dark toggle**: light outside a meeting, dark inside a room. Those are two ramps, both live at once.

Every brand pairing must clear WCAG AA. The raw Kodera values do not — `#FD6262` on white is **2.96:1** and `#889CE7` on white is **2.64:1**, failing both the 4.5:1 text and 3:1 non-text thresholds. `theme/custom.css` darkens the fill and text steps while keeping coral as a decorative accent. `scripts/check-contrast.py` enforces this in CI; run it after any palette edit.

### Assets

Bind-mount branding assets **per file**. Never mount a *directory* over `/usr/share/nginx/html/assets` — that replaces Vite's build output and the app will not boot. Favicons and PWA icons live at the web **root**, not under `/assets`.

The browser-tab title needs a rebuilt frontend image (`VITE_APP_TITLE`), which contradicts the no-fork position; **accept the upstream title for v1.** Note it appears in on-screen copy too, not only the tab.

**Credit upstream visibly.** MIT requires the notice — see [`NOTICE.md`](NOTICE.md) — and good faith requires the link. There is no footer element to hang it on (`use_french_gov_footer` defaults false and `Footer.tsx:125` returns `null`), so the theme injects it via `.Header-beforeLogo::after`. CSS `content` cannot carry a clickable link, so the landing page (§7bis) carries the clickable one.

---

## 7bis. The public landing page

Anonymous visitors get **our** home page; signed-in users keep Meet's; rooms are
untouched upstream UI. This is an upstream-supported mechanism, not a fork.

| URL | Visitor | Serves |
|---|---|---|
| `/` | anonymous | redirected to `/accueil/` — our landing |
| `/` | signed in | Meet's home (create instant / scheduled room) |
| `/<slug>` | anyone | the DINUM room UI, unchanged |

**How it works.** `FRONTEND_EXTERNAL_HOME_URL` (`settings.py:401`) is published
in `/api/v1.0/config/` as `external_home_url`. `Home.tsx:165-175` reads it,
sends a `HEAD` probe, and only then calls `window.location.replace()` — so the
URL **must be reachable from the visitor's browser**. Keep it same-origin:
that is also what keeps the address bar on `visio.samourai.app`.

The page itself is [`landing/index.html`](landing/index.html) — one
self-contained file, no build step, no framework. Copy the directory to
`~/visio/landing/`; `compose.override.yaml` mounts it at
`/usr/share/nginx/html/accueil`.

> [!WARNING]
> **Same silent failure as the CSS.** The frontend nginx ends with
> `error_page 404 =200 /index.html`, so a missing mount returns **200
> text/html** — the SPA — not a 404. The visitor is then bounced from `/` back
> into the app, which reads exactly like a redirect loop and gets debugged as
> an auth problem. `preflight.sh public` asserts on the *content* of the page,
> never on the status code.

> [!NOTE]
> Mounting a **directory** is safe here, unlike `/assets` above, because
> `accueil` does not exist in the image — nothing is shadowed. The nginx
> `try_files $uri $uri/ /index.html` resolves the directory to its
> `index.html`. Keep the **trailing slash** in the env var or nginx spends a
> 301 redirect adding it.

The "Démarrer une réunion" button generates a slug client-side and navigates to
it — no API call. That works only because `ALLOW_UNREGISTERED_ROOMS=True`
materialises the room on arrival (§4 trap 1). The slug format is upstream's
own (`abc-defg-hij`, lowercase, 3-4-3); a different shape would not match the
room route's regex. It is generated with `crypto.getRandomValues`, not
`Math.random`, because the slug *is* the access secret for the room.

To hand the front door back to upstream, unset the variable **and** re-run
`docker compose up -d` (a `restart` does not reload env). Then remove
`landing/` from the host, or `preflight.sh config` turns red on the
files-without-a-URL case it is designed to catch.

### The legal pages ship with it

`landing/` also carries `mentions-legales/`, `confidentialite/` and
`conditions-utilisation/`, served under `/accueil/`.

> [!WARNING]
> **Never link to `/mentions-legales`, `/conditions-utilisation` or
> `/accessibilite` at the site root.** Those routes are upstream's, and the SPA
> hardcodes DINUM's own notices on them: DINUM as publisher with the French
> State's SIREN `120 001 011`, a serving public official as *directrice de la
> publication*, Outscale as host, a service reserved for State administrations,
> and DINUM's RGAA accessibility declaration. **No environment variable
> overrides them.** Two defences: `scripts/check-hygiene.sh` fails the build if
> anything under `landing/` links to them, and the gateway override
> ([`deploy/nginx/default.conf.template`](deploy/nginx/default.conf.template))
> answers all three routes with a **301 to our pages** before the SPA can —
> `preflight.sh public` asserts the redirects, and
> `check-upstream-contract.sh` pins the template against upstream so gateway
> drift cannot ship silently on a version bump (§10).

### No third-party resource, and it is enforced

The landing and the privacy policy both state that the service loads nothing
from a third party. That is now a gate, not a promise: `check-hygiene.sh`
rejects any `@import`, `url()`, `<script src>`, `<link href>` or `<iframe>`
pointing off-origin in `theme/custom.css` or `landing/`, and
`preflight.sh public` re-checks the **deployed** theme, which an operator may
have edited on the host. A font `@import` in the theme did exactly this once —
it leaked every visitor's IP and User-Agent on every page, rooms included.

---

## 8. Smoke tests

- [ ] `https://visio.samourai.app` loads over TLS
- [ ] Resolved settings are what you wrote — **run this before touching login**:
      ```bash
      docker compose run --rm backend python manage.py shell -c \
        "from django.conf import settings; print(settings.OIDC_USERINFO_FULLNAME_FIELDS, settings.OIDC_REDIRECT_ALLOWED_HOSTS)"
      ```
      Expected `['given_name', 'family_name'] ['visio.samourai.app']`. Anything with a bracket in it is trap 2.
- [ ] `X-Forwarded-Proto` cannot be spoofed — `curl -H "X-Forwarded-Proto: https" http://visio.samourai.app/` must redirect to `https://`, not serve a 200 over plaintext
- [ ] "Log in" → Clerk → back to Meet, **name and email correct** (validates traps 3 and 4). Test with a **freshly created** account: a pre-existing Clerk user may simply have no name stored
- [ ] Anonymous first visit does not bounce — silent login (`prompt=none`) succeeds or fails gracefully
- [ ] Create a room as a logged-in user
- [ ] Open the **created** room's link in a private window — joins with no account *(validates `access_level` + `RoomPermissions`, **not** the flag)*
- [ ] Open a slug that was **never created** — e.g. `/zzz-test-unregistered-2026` — in a private window; a room materialises and joins *(**this alone** validates `ALLOW_UNREGISTERED_ROOMS` — trap 1)*
- [ ] 3-way call: audio, video, screenshare
- [ ] Mobile browser, iOS Safari + Android Chrome
- [ ] Call from a restrictive network (mobile data / corporate VPN). **Records what works; not a pass/fail gate.** With TURN on UDP/443 this covers firewalls that permit QUIC; a TCP-443-only firewall with TLS inspection will still fail, and that needs a second IP or SNI multiplexing
- [ ] Invitation email arrives via Scaleway TEM, **and its logo renders**
- [ ] Custom CSS **applied**, not merely served — `/custom/style.css` must return `200 text/css`; the SPA fallback returns `200 text/html` for a missing file, never 404
- [ ] **Landing page** — open `https://visio.samourai.app/` in a private window: you land on the Samouraï page, not Meet's home. Then sign in and open `/` again: you get **Meet's** home. Both halves matter (§7bis)
- [ ] **Legal pages reachable** from the landing footer, and they name **Samouraï Coop** — not DINUM (§7bis)
- [ ] **No third-party request** — open devtools → Network on the landing *and* inside a room, and confirm every request goes to `visio.samourai.app` or `livekit.samourai.app`. This is what the privacy policy asserts
- [ ] **A guest never contacts Clerk** — with `FRONTEND_IS_SILENT_LOGIN_ENABLED=false`, an anonymous first visit must produce no `clerk.samourai.app` request and leave no `silent-login-retry` key in `localStorage`
- [ ] **"Démarrer une réunion" works** — the button lands you in a joinable room. This also re-exercises `ALLOW_UNREGISTERED_ROOMS`
- [ ] **Backend default locale is `fr-fr`** — `/api/v1.0/config/` reports it. This needs the container **recreated** (`up -d`), not merely restarted.
      ⚠️ It does **not** set the interface language: the SPA resolves that client-side via i18next browser detection (`localStorage`, then `navigator`; `fallbackLng: 'fr'`), and `LANGUAGE_CODE` appears in none of its JS chunks. Invitation e-mails follow the **sender's** `Accept-Language`. Check the UI language in a browser set to French — there is no server-side switch for it
- [ ] `/admin` reachable, non-admins rejected
- [ ] Reboot the host. All five services plus nginx-proxy return unattended, TLS still serves, a room still joins
- [ ] `docker compose restart redis` → still logged in *(proves the AOF volume took)*

---

## 8bis. Log retention — the privacy policy's 7-day clock

The privacy policy (`landing/confidentialite/`) states that IP-bearing
technical logs are kept **7 days, then deleted**. Docker's default json-file
driver cannot honour a time bound — it rotates by **size** only, so at low
traffic it retains entries for months. Every container therefore logs to
**journald**, and journald enforces the clock. Three pieces:

| Piece | File | Covers |
|---|---|---|
| Compose logging anchor | [`deploy/compose.override.yaml`](deploy/compose.override.yaml) | the five stack services |
| Docker daemon default | [`deploy/host/daemon.json`](deploy/host/daemon.json) | every other container — **nginx-proxy logs every client IP** |
| journald drop-in | [`deploy/host/visio-retention.conf`](deploy/host/visio-retention.conf) | the clock itself: `MaxRetentionSec=7day`, daily rotation, persistent storage, 1 GB ceiling |

Install, on the host:

```bash
# 1. journald: the 7-day clock
sudo cp deploy/host/visio-retention.conf /etc/systemd/journald.conf.d/
sudo systemctl restart systemd-journald

# 2. Docker daemon default. MERGE if /etc/docker/daemon.json already exists —
#    deploy/host/daemon.json also carries userland-proxy:false, which the
#    published TURN relay range wants anyway (see compose.override.yaml).
sudo cp deploy/host/daemon.json /etc/docker/daemon.json
sudo systemctl restart docker      # containers return via restart policies

# 3. The stack: the override sets `driver: journald`; recreation applies it.
docker compose up -d               # recreates on config change — NOT `restart`

# 4. nginx-proxy lives in its own compose project and keeps the driver it was
#    CREATED with — daemon.json is only read at creation. Recreate it:
(cd ~/proxy && docker compose up -d --force-recreate)

# 5. Purge the backlog accumulated before the clock existed. The old
#    json-file logs die with the recreated containers.
sudo journalctl --rotate && sudo journalctl --vacuum-time=7d

# 6. rsyslog keeps FILE copies (auth.log, kern.log) on the distro default of
#    weekly × 4 ≈ up to 5 weeks. Tighten them to daily × 7:
sudo sed -i 's/weekly/daily/; s/rotate 4/rotate 7/' /etc/logrotate.d/rsyslog
```

Verify — `preflight.sh config` asserts the files, `preflight.sh stack` the
runtime:

```bash
docker ps -q | xargs docker inspect -f '{{.Name}} {{.HostConfig.LogConfig.Type}}'
# every line must end in "journald" — a container created before the change
# keeps json-file forever; a restart does not fix it, only recreation does
journalctl -q -o short-unix | head -1   # oldest surviving entry: ≤ 8 days old
```

`docker compose logs` keeps working — the journald driver supports it.

> [!NOTE]
> The page's two other retention promises are **by construction**, not by
> machinery, since the 2026-07-24 rewording: rooms created without an account
> are never written to the database at all (`core/api/viewsets.py:257-277`
> builds the response in memory — asserted by `check-upstream-contract.sh`),
> and account deletion is **on request** — deliberately, because a Samouraï
> account is shared across apps, so an idle-on-Visio timer would delete
> accounts still active on Memba or Zentai.

---

## 9. Before you promote it

A free public WebRTC service with open signup is a bandwidth and moderation liability. Have these live **before** any announcement:

- [x] **Mentions légales** (LCEN art. 6-III) and **politique de confidentialité** (GDPR art. 13) — published at `/accueil/mentions-legales/` and `/accueil/confidentialite/`, naming Samouraï Coop as publisher and Scaleway SAS as host. Abuse contact `support@samourai.coop` is on both.
- [ ] **Run the §8bis install block on the host.** The config, the gates and the page now agree — logs are deleted after 7 days by journald, guest rooms are never stored at all, accounts are deleted on request — but the journald half only exists once §8bis has been executed on the host. `preflight.sh` fails until it has.
- [ ] **Caps** — max participants per room, max room duration. Meet exposes neither; enforce LiveKit-side (`max_participants`, `empty_timeout`).
- [ ] **CGU: copy `deploy/nginx/` to the host with the rest.** Our own conditions are written (`landing/conditions-utilisation/`), and the gateway override 301s upstream's three DINUM routes to our pages (§7bis) — but both only exist on the host once `landing/` and `nginx/` are copied and the stack recreated. `preflight.sh public` asserts the page and the redirects.
- [ ] **Backups** — `pg_dump` on a cron, off-box
- [ ] **Monitoring** — Sentry already runs at `sentry.samourai.pro`; add uptime + a bandwidth alert
- [ ] **Bandwidth ceiling** — know the number at which you throttle or pay, and decide in advance which

---

## 10. Upgrades

> [!WARNING]
> `docker compose restart` does **not** apply a newly pulled image. A container's image is bound at creation, so `restart` reuses the existing container and the pulled layers are never used — then `migrate` runs new migrations against old code. Use `up -d`.

```bash
# 1. Read UPGRADE.md and CHANGELOG.md between the pinned tag and the target.
#    Re-run the contract gate against the target tag before anything else:
scripts/check-upstream-contract.sh v1.25.0

# 2. BACK UP FIRST — this is the only rollback that exists.
docker compose exec -T postgresql pg_dump -U meet meet \
  | gzip > ~/backups/pre-upgrade-$(date +%F-%H%M).sql.gz
ls -lh ~/backups/pre-upgrade-*.sql.gz | tail -1     # non-zero size, or stop

# 3. Record the current state so you can get back to it.
docker compose config --images > ~/backups/images-$(date +%F-%H%M).txt
docker compose run --rm backend python manage.py showmigrations \
  > ~/backups/migrations-$(date +%F-%H%M).txt

# 4. If the contract gate flagged the gateway template, re-derive it now:
#    fresh upstream default.conf.template + the SAMOURAI-marked blocks, into
#    deploy/nginx/default.conf.template (then copy to ~/visio/nginx/).
#
# 5. Bump the tags in compose.override.yaml (NOT compose.yaml — that gets
#    re-fetched verbatim), then:
docker compose pull
docker compose up -d          # NOT `restart`
docker compose config --images   # confirm the new tags are actually running
docker compose run --rm backend python manage.py migrate
```

**Rollback:** revert the tags in `compose.override.yaml`, `docker compose up -d`, then restore the dump if the migration was not reversible. Re-fetch upstream `compose.yaml` at the old tag if it changed.

### Rotating a secret

No secret rotates cleanly by itself — each has a blast radius:

| Secret | Rotation effect |
|---|---|
| `DJANGO_SECRET_KEY` | invalidates every session — **mass logout, mid-call** |
| `LIVEKIT_API_SECRET` | must change in **two** files (`env.d/common` *and* `livekit-server.yaml`) or every token fails signature validation and nobody can join |
| `DB_PASSWORD` | change in PostgreSQL *and* `env.d/postgresql` |
| `OIDC_RP_CLIENT_SECRET` | regenerate in Clerk; login is broken between regeneration and restart |
| Scaleway TEM API key | invitation emails fail silently until restart |
