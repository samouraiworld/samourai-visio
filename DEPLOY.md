# Deploying visio.samourai.app — operator quickstart

For whoever runs the deploy. This is the linear path; [RUNBOOK.md](RUNBOOK.md) is
the detail behind each step, and `scripts/preflight.sh` is the gate that proves
each stage is actually correct — not just "up".

> **The stack fails silently when misconfigured.** A wrong env-var name, a JSON
> list, a mismatched LiveKit key, or a missing mount all give you a green
> `docker compose ps` and broken behaviour. Run preflight at each gate and trust
> it over appearances. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Two ways to deploy

- **Manual (this document).** A Scaleway host you control, Docker Compose,
  nginx-proxy for TLS. Full control, ready now — follow the steps below.
- **Via Greffon** ([deploy/greffon/](deploy/greffon/README.md)). Package the stack as a
  [Greffon](https://greffon.io) catalog app: Greffon provides the reverse proxy,
  TLS, and secret generation, and Visio joins its catalogue. A draft entry
  exists; it is **gated on Greffon supporting a stable custom domain** (Clerk's
  redirect URI is fixed), so until that's confirmed the manual path is the one
  that works. The two are not exclusive — you can launch manually now and move
  to Greffon later without redoing Clerk or DNS.

The rest of this document is the manual path.

---

## 0. Before you touch the server — collect from the owner

Nothing past step 2 works without these. Get them first.

| # | Need | Notes |
|---|---|---|
| 0.1 | **Clerk: shared org or dedicated instance?** | **Decide first — it sets the OIDC endpoints and can't be changed after step 3 without invalidating accounts.** Default so far: the shared `clerk.samourai.app` org. |
| 0.2 | **Server IP + SSH access** | The host to deploy on. |
| 0.3 | **Clerk OAuth app** → `OIDC_RP_CLIENT_ID` + secret | Register redirect URI **exactly** `https://visio.samourai.app/api/v1.0/callback/`. Scopes `openid email profile`. Secret is shown once. |
| 0.4 | **Clerk: enable `username`** | Without it, every display name is empty — see [docs/CLERK_INSTANCE_AUDIT_2026-07-22.md](docs/CLERK_INSTANCE_AUDIT_2026-07-22.md). Owner action in the Clerk dashboard. |
| 0.5 | **Scaleway TEM** — a verified sending domain + an API key | Invitation emails, via Scaleway Transactional Email (French/EU). Verify the domain in TEM (SPF + DKIM + DMARC on the shared apex — coordinate it); username is the Project ID, password the API secret key. |
| 0.6 | **Brand assets** | `logo.png` for emails; favicons. The CSS theme is already in the repo (`theme/custom.css`). |

DNS (owner or ops): `visio.samourai.app` **and** `livekit.samourai.app` → the
instance IP (A records, no stray AAAA/CAA — see RUNBOOK §2).

---

## 1. Host prerequisites

```bash
ssh "$HOST" 'docker --version && docker compose version && nproc && free -g | head -2'
```

- Docker + **Compose v2** (v1 has different `env_file` semantics).
- ≥ 4 vCPU / 16 GB (RUNBOOK §2).
- Firewall **and** Scaleway security group both open: `80/tcp 443/tcp 443/udp 7881/tcp 7882/udp 30000-30100/udp`. The security group is a second filter `ufw status` can't see — a green ufw with a closed security group is the #1 cause of "signalling works, no media".

---

## 2. Configure

```bash
mkdir -p ~/visio && cd ~/visio
```

1. Fetch upstream verbatim — **RUNBOOK §3** (`compose.yaml`, `.env`, `env.d/*`, `livekit-server.yaml`, `default.conf.template`).
2. Copy this repo's templates and fill every value — **RUNBOOK §4**:
   - `deploy/env.d/common.example` → `env.d/common`
   - `deploy/env.d/postgresql.example` → `env.d/postgresql`
   - `deploy/hosts.example` → `.env`
   - `deploy/livekit-server.yaml.example` → `livekit-server.yaml`
   - `deploy/compose.override.yaml` → `compose.override.yaml` (our deltas; **never edit `compose.yaml`**)
3. Branding: copy `theme/custom.css` → `custom/style.css`, `logo.png` → `custom/logo.png`, and the icon set `theme/icons/*` → `custom/icons/` (nine files, bind-mounted per file — RUNBOOK §7).
   Then copy this repo's `landing/` directory → `~/visio/landing/` — that's the
   public home page anonymous visitors get instead of Meet's (RUNBOOK §7bis).
   It is served same-origin, so the URL stays on `visio.samourai.app`.
4. Generate the three secrets — **RUNBOOK §3**. Note `DJANGO_SECRET_KEY` needs `openssl rand -base64 64 | tr -d '\n'` (it wraps otherwise).

### GATE — config

```bash
scripts/preflight.sh config
```

Must be all-green before you start anything. It catches the silent ones:
placeholders left unfilled, JSON-shaped lists, the LiveKit key mismatch, a
Keycloak logout endpoint copied by accident, missing branding assets, floating
image tags, TURN misconfig.

---

## 3. Reverse proxy + TLS — RUNBOOK §5

- `docker network create proxy-tier`
- Deploy the nginx-proxy example in **its own** compose project, with the two mandatory edits: `DEFAULT_EMAIL` (a monitored address) and **`TRUST_DOWNSTREAM_PROXY=false`** (or a client can spoof the scheme Django trusts).
- **First issuance against Let's Encrypt _staging_**, then switch to production — the apex is shared, don't burn the rate limit.

## 4. Launch — RUNBOOK §6

```bash
docker compose up -d
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py createsuperuser --email <admin@samourai.app>
```

### GATE — stack

```bash
scripts/preflight.sh stack
```

Confirms the backend is healthy, env interpolation resolved (empty ≠ literal
`${VAR}`), the resolved Django settings actually parse (this is where the JSON-list
bug would show), Redis persistence is on, and migrations are applied.

---

## 5. Verify the live surface

### GATE — public

```bash
scripts/preflight.sh public
```

DNS, TLS on both hosts, no redirect loop on `/api`, **scheme-spoof rejected**,
`/custom/style.css` served as `text/css` (not the SPA's `200 text/html`), the
backend advertising `custom_css_url`, and — the one test that actually exercises
`ALLOW_UNREGISTERED_ROOMS` — an **unknown** slug materialising a room.

Then walk **RUNBOOK §8** by hand for the things a script can't prove: a real
3-way call (audio/video/screen-share), mobile browsers, a restrictive network,
the invitation email + its logo, and `/admin` rejecting non-admins.

Preflight prints `SKIP` for what it structurally cannot check (UDP reachability,
the Scaleway security group, silent-login in a real browser). **SKIP means
unproven, not fine** — read each one.

---

## If something's wrong

`preflight.sh` names the exact failure and the reason. Don't proceed past a red
gate — every check maps to a real, already-seen failure mode documented in
[docs/CTO_REVIEW_2026-07-22.md](docs/CTO_REVIEW_2026-07-22.md). The usual first
suspects: a surviving `<placeholder>`, a wrapped secret, or the Scaleway
security group.

Rollback and upgrades: **RUNBOOK §10** (back up with `pg_dump` before any
`migrate`; use `docker compose up -d`, never `restart`).

Before any public promotion: **RUNBOOK §9** (retention, caps, CGU + *mentions
légales* + privacy policy, backups, monitoring).
