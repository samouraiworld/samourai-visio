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

# ── Mail (Resend) ──
DJANGO_EMAIL_HOST=smtp.resend.com
DJANGO_EMAIL_HOST_USER=resend
DJANGO_EMAIL_HOST_PASSWORD=<resend api key>
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
OIDC_USERINFO_FULLNAME_FIELDS=given_name,family_name
OIDC_USERINFO_SHORTNAME_FIELD=given_name
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

**3. `OIDC_USERINFO_FULLNAME_FIELDS` — you must override the default.**
Meet defaults to `["given_name", "usual_name"]` (`settings.py:574`). `usual_name` is a **ProConnect-specific** claim; Clerk does not emit it (see §1 `claims_supported`). Leave the default and every user's display name is broken. Set `given_name,family_name` — obeying trap 2.

**4. `OIDC_RP_SCOPES` — the default is too narrow.**
Default is `"openid email"` (`settings.py:533`). Without `profile` you get no `given_name`/`family_name` and names render empty regardless of trap 3. Note that the scope is necessary but **not sufficient**: Clerk emits these claims only if the *instance* collects first/last name, which is a setting shared with every other `*.samourai.app` product.

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

**Credit upstream visibly.** MIT requires the notice — see [`NOTICE.md`](NOTICE.md) — and good faith requires the link. There is no footer element to hang it on (`use_french_gov_footer` defaults false and `Footer.tsx:125` returns `null`), so the theme injects it via `.Header-beforeLogo::after`. CSS `content` cannot carry a clickable link, so put the repo link on the promo page as well.

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
- [ ] Invitation email arrives via Resend, **and its logo renders**
- [ ] Custom CSS **applied**, not merely served — `/custom/style.css` must return `200 text/css`; the SPA fallback returns `200 text/html` for a missing file, never 404
- [ ] `/admin` reachable, non-admins rejected
- [ ] Reboot the host. All five services plus nginx-proxy return unattended, TLS still serves, a room still joins
- [ ] `docker compose restart redis` → still logged in *(proves the AOF volume took)*

---

## 9. Before you promote it

A free public WebRTC service with open signup is a bandwidth and moderation liability. Have these live **before** any announcement:

- [ ] **Retention policy** — monthly reset of rooms/accounts. This is what `visio.lasuite.coop` does; it's a proven, defensible norm and it caps storage growth.
- [ ] **Caps** — max participants per room, max room duration
- [ ] **CGU + abuse contact** published
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

# 4. Bump the tags in compose.override.yaml (NOT compose.yaml — that gets
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
| Resend API key | invitation emails fail silently until restart |
