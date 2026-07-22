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

- `ALLOW_UNREGISTERED_ROOMS=True` → **guests join by link with no account**
- Clerk login required only to **create/own** a room
- Django session cookie, 12 h

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
ufw allow 80/tcp      # TLS issuance
ufw allow 443/tcp     # HTTPS + TURN/TLS
ufw allow 443/udp     # TURN/TLS
ufw allow 7881/tcp    # WebRTC ICE over TCP
ufw allow 7882/udp    # WebRTC multiplexing over UDP
ufw enable
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
openssl rand -base64 48   # DB_PASSWORD
openssl rand -base64 48   # LIVEKIT_API_SECRET
openssl rand -base64 64   # DJANGO_SECRET_KEY
```

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

OIDC_USERINFO_FULLNAME_FIELDS=["given_name","family_name"]
OIDC_USERINFO_SHORTNAME_FIELD=given_name

OIDC_USE_PKCE=true
OIDC_PKCE_CODE_CHALLENGE_METHOD=S256
OIDC_CREATE_USER=true
OIDC_REDIRECT_REQUIRE_HTTPS=true
OIDC_REDIRECT_ALLOWED_HOSTS=["https://${MEET_HOST}"]

LOGIN_REDIRECT_URL=https://${MEET_HOST}
LOGIN_REDIRECT_URL_FAILURE=https://${MEET_HOST}
LOGOUT_REDIRECT_URL=https://${MEET_HOST}

# ── LiveKit ──
LIVEKIT_API_SECRET=<generated>
LIVEKIT_API_KEY=meet
LIVEKIT_API_URL=https://${LIVEKIT_HOST}

# ── Public instance ──
ALLOW_UNREGISTERED_ROOMS=True

# ── Branding ──
FRONTEND_CSS_URL=/custom/style.css
```

### Three config traps

**1. `OIDC_USERINFO_FULLNAME_FIELDS` — you must override the default.**
Meet defaults to `["given_name", "usual_name"]` (`settings.py:505`). `usual_name` is a **ProConnect-specific** claim; Clerk does not emit it (see §1 `claims_supported`). Leave the default and every user's display name is broken. Set it to `["given_name","family_name"]`.

**2. `OIDC_RP_SCOPES` — the default is too narrow.**
Default is `"openid email"` (`settings.py:464`). Without `profile` you get no `given_name`/`family_name` and names render empty regardless of trap #1.

**3. No logout endpoint.**
Clerk reports `backchannel_logout_supported: false` and `frontchannel_logout_supported: false`. Leave `OIDC_OP_LOGOUT_ENDPOINT` unset. Consequence: signing out of Meet clears the local Django session but **not** the Clerk SSO session — clicking "log out" then "log in" silently re-authenticates. Acceptable for a shared-SSO product; surprising if you don't expect it. If you need true logout, redirect to Clerk's sign-out URL after `LOGOUT_REDIRECT_URL`.

### `livekit-server.yaml`

Set the same `LIVEKIT_API_SECRET` against key `meet`.

The example multiplexes WebRTC on a **single UDP port**. A **port range** performs materially better under load — worth doing before any public promotion, and it means opening that range in §2.

### Pin your images

`compose.yaml` ships `latest` on every service. Pin every tag to a released version, or an upstream push will silently restart your production stack on the next `docker compose pull`.

---

## 5. Reverse proxy + TLS

Use the upstream [nginx-proxy example](https://github.com/suitenumerique/meet/tree/main/docs/examples/compose/nginx-proxy) (auto Let's Encrypt). Uncomment the `environment:` and `networks:` blocks in `compose.yaml`:

```yaml
  frontend:
    environment:
      - VIRTUAL_HOST=${MEET_HOST}
      - VIRTUAL_PORT=8083
      - LETSENCRYPT_HOST=${MEET_HOST}
    networks:
      - proxy-tier
      - default

  livekit:
    environment:
      - VIRTUAL_HOST=${LIVEKIT_HOST}
      - VIRTUAL_PORT=7880
      - LETSENCRYPT_HOST=${LIVEKIT_HOST}
    networks:
      - proxy-tier
      - default

networks:
  proxy-tier:
    external: true
```

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

`FRONTEND_CSS_URL` injects CSS at runtime via a `<link>` in `<head>` — **no rebuild, no fork, survives upgrades**. Serve `custom/style.css` from the frontend container or any URL.

Starter using the Kodera tokens from `samourai.world-v2026`:

```css
/* Samouraï Visio — runtime theme over La Suite Meet */
:root {
  --c--theme--colors--primary-500: #FD6262;   /* coral   */
  --c--theme--colors--primary-600: #E85454;
  --c--theme--colors--secondary-500: #889CE7; /* lavender */
  --c--theme--colors--greyscale-1000: #141416;
  --c--theme--font--families--base: 'Inter', system-ui, sans-serif;
}
```

> Token names are indicative — confirm against the live DOM and `docs/theming.md`, since Cunningham's variable names drift between versions. Inspect the running app and adjust.

Build-time env vars cover the browser-tab app name.

**Credit upstream visibly.** MIT requires the licence; good faith requires the link. A "Propulsé par La Suite Meet" line in the footer is the difference between running La Suite for people who have no server, and looking like a rebrand.

---

## 8. Smoke tests

- [ ] `https://visio.samourai.app` loads over TLS
- [ ] "Log in" → Clerk → back to Meet, **name and email correct** (validates traps #1 and #2)
- [ ] Create a room as a logged-in user
- [ ] **Open the room link in a private window — joins with no account** (validates `ALLOW_UNREGISTERED_ROOMS`)
- [ ] 3-way call: audio, video, screenshare
- [ ] Mobile browser, iOS Safari + Android Chrome
- [ ] Call from a restrictive network (mobile data / corporate VPN) — proves TURN over 443 works
- [ ] Invitation email arrives via Resend
- [ ] Custom CSS applied
- [ ] `/admin` reachable, non-admins rejected

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

```bash
# 1. read UPGRADE.md and CHANGELOG.md first
# 2. bump the pinned tags in compose.yaml
docker compose pull
docker compose restart
docker compose run --rm backend python manage.py migrate
```
