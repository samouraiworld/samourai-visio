# visio.samourai.app — Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Status: PROPOSAL — awaiting owner review. Nothing in Phases B–J has been executed.**
> Evidence base: [DRIFT_REPORT_2026-07-22.md](DRIFT_REPORT_2026-07-22.md). Read it first; this plan assumes its findings.

**Goal:** Bring La Suite Meet live at `visio.samourai.app`, authenticated against the existing Clerk org, with working guest-join, working branding, and an honest account of what does and does not work on restrictive networks.

**Architecture:** Single Scaleway host. Docker Compose, five services (PostgreSQL, Redis, LiveKit, Meet backend, Meet frontend) behind nginx-proxy with Let's Encrypt. Clerk is the external OIDC provider — no Keycloak. All of our deltas live in `compose.override.yaml` so upstream's `compose.yaml` stays pristine and re-fetchable at upgrade time. No fork of the application.

**Tech Stack:** Docker Compose v2, Django 5 (`django-configurations`), `django-lasuite` + `mozilla-django-oidc`, LiveKit SFU, PostgreSQL 16, Redis, Panda CSS (frontend design tokens), nginx-proxy + acme-companion.

---

## Global Constraints

- **Never commit to `main`/`master`.** Feature branches + PR only. No Claude attribution in commits, PR bodies, tags, or release notes.
- **Secrets live only in gitignored files.** Tracked files carry `*.example` placeholders and nothing else. The Clerk client secret is displayed once and is unrecoverable.
- **`FRONTEND_CUSTOM_CSS_URL`** is the correct variable name. `FRONTEND_CSS_URL` does not exist.
- **Design tokens are Panda CSS** (`--colors-*`, `--fonts-*`). Cunningham `--c--theme--*` names are dead.
- **Pin every image tag.** No `latest` reaches the host.
- **Upstream `compose.yaml` is read-only**, re-fetched verbatim at upgrade. Our changes go in `compose.override.yaml`.
- **Verify-first.** Infrastructure has no unit tests, so every task states its check, runs it *before* the change to observe the failure, then runs it again to observe the pass. A task without an executed check is not done.
- **Attribution stays visible.** "Propulsé par La Suite Meet" with a link to `suitenumerique/meet` must survive every theme change.
- Target versions as of 2026-07-22: `lasuite/meet-backend:v1.24.0`, `lasuite/meet-frontend:v1.24.0`, `livekit/livekit-server:v1.13.4`, `postgres:16`, `redis:7-alpine`.

---

## Phase A — Repository corrections (no server required)

> These three tasks fix defects that exist in the repo *today*. They need no IP, no credentials, and no host. They can land before any infrastructure work and should, because they are what makes Phase H succeed on the first attempt.

### Task A1: Correct the CSS variable name

**Files:**
- Modify: `deploy/env.d/common.example:67`
- Modify: `RUNBOOK.md:207`
- Verify: `docs/DRIFT_REPORT_2026-07-22.md` (BLOCKER-1)

**Interfaces:**
- Produces: `FRONTEND_CUSTOM_CSS_URL` as the canonical name used by Tasks D2, H2, I6.

- [ ] **Step 1: Confirm the defect is still live upstream**

```bash
curl -s https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/src/backend/meet/settings.py \
  | grep -n "CUSTOM_CSS_URL\|FRONTEND_CSS_URL"
```

Expected: one hit, `environ_name="FRONTEND_CUSTOM_CSS_URL"`. Zero hits for `FRONTEND_CSS_URL`.

- [ ] **Step 2: Fix the template**

In `deploy/env.d/common.example`, replace the `# ── Branding ──` block:

```env
# ── Branding ──
# NB: the variable is FRONTEND_CUSTOM_CSS_URL, not FRONTEND_CSS_URL.
# Django silently ignores unknown env vars — a wrong name here produces a
# healthy stack with no theme and no error message anywhere.
# Served by the bind-mount in compose.override.yaml (see RUNBOOK §7).
FRONTEND_CUSTOM_CSS_URL=/custom/style.css
```

- [ ] **Step 3: Fix the runbook**

In `RUNBOOK.md` §4, replace `FRONTEND_CSS_URL=/custom/style.css` with `FRONTEND_CUSTOM_CSS_URL=/custom/style.css`. In §7, replace the sentence `` `FRONTEND_CSS_URL` injects CSS at runtime `` with `` `FRONTEND_CUSTOM_CSS_URL` injects CSS at runtime ``.

- [ ] **Step 4: Verify no occurrence survives**

```bash
grep -rn "FRONTEND_CSS_URL" . --exclude-dir=.git
```

Expected: no output (exit 1).

- [ ] **Step 5: Commit**

```bash
git add deploy/env.d/common.example RUNBOOK.md
git commit -m "Use FRONTEND_CUSTOM_CSS_URL — FRONTEND_CSS_URL is not a Meet setting and fails silently"
```

---

### Task A2: Rewrite the theme against Panda CSS tokens

**Files:**
- Rewrite: `theme/custom.css`
- Modify: `RUNBOOK.md` §7 (the starter CSS block)

**Interfaces:**
- Consumes: `FRONTEND_CUSTOM_CSS_URL` from Task A1.
- Produces: `theme/custom.css`, mounted at `/custom/style.css` by Task D3, verified by Task I6.

- [ ] **Step 1: Re-derive the token names from source**

```bash
curl -s https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/src/frontend/panda.config.ts \
  | grep -n "primaryDark\|primary:\|greyscale:\|semanticTokens\|fonts:"
```

Expected: `primaryDark` and `primary` colour ramps, a `greyscale` ramp `000`–`1000`, a `semanticTokens` block, and a `fonts` block. Confirms Panda, not Cunningham.

- [ ] **Step 2: Replace `theme/custom.css` entirely**

```css
/* ─────────────────────────────────────────────────────────────
   Samouraï Visio — runtime theme over La Suite Meet
   Loaded via FRONTEND_CUSTOM_CSS_URL. No rebuild, no fork.

   Token authority: src/frontend/panda.config.ts (Panda CSS).
   Meet migrated OFF Cunningham — `--c--theme--*` names are dead
   and fail silently. See docs/DRIFT_REPORT_2026-07-22.md.

   Meet has no light/dark toggle: LIGHT outside a meeting,
   DARK inside a room. Those are two different palettes.
   ───────────────────────────────────────────────────────────── */

:root {
  /* ── Outside the room: light surface ── */
  --colors-primary: #FD6262;          /* Kodera coral */
  --colors-primary-hover: #E85454;
  --colors-primary-active: #A63A3A;
  --colors-primary-text: #FFFFFF;
  --colors-primary-subtle: #FFE9E9;
  --colors-primary-subtle-text: #A63A3A;

  /* ── Inside the room: dark surface ──
     Panda's primaryDark ramp runs 50 (darkest) → 950 (lightest). */
  --colors-primary-dark-50: #141416;  /* Kodera background */
  --colors-primary-dark-500: #FD6262;
  --colors-primary-dark-action: #FE9A9A;

  /* ── Type ── */
  --fonts-sans: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
}

/* Attribution — MIT requires the licence, good faith requires the link.
   Keep this visible: it's the difference between running La Suite for
   people who have no server, and looking like a rebrand. */
.samourai-credit {
  font-size: 0.75rem;
  opacity: 0.65;
  text-align: center;
  padding: 0.5rem;
}
.samourai-credit a { color: inherit; text-decoration: underline; }
```

> The secondary lavender `#889CE7` is deliberately dropped: Panda exposes no `secondary` semantic token. Reintroduce it only against a token confirmed in the live DOM (Task H3).

- [ ] **Step 3: Update the runbook's starter block**

Replace the CSS block in `RUNBOOK.md` §7 with the `:root` block above, and replace the note *"Token names are indicative — confirm against the live DOM and `docs/theming.md`, since Cunningham's variable names drift between versions"* with:

```markdown
> Tokens are **Panda CSS** (`src/frontend/panda.config.ts`), not Cunningham.
> Meet has no light/dark toggle — light outside a meeting, dark in a room.
> Confirm every token against the live DOM before calling the theme done (§8).
```

- [ ] **Step 4: Verify no dead token survives**

```bash
grep -rn -- "--c--theme--" . --exclude-dir=.git
```

Expected: no output (exit 1).

- [ ] **Step 5: Commit**

```bash
git add theme/custom.css RUNBOOK.md
git commit -m "Retarget theme at Panda CSS tokens — Meet migrated off Cunningham, every --c--theme--* rule was a no-op"
```

---

### Task A3: Reconcile the `ALLOW_UNREGISTERED_ROOMS` documentation and fix the smoke test

**Files:**
- Modify: `RUNBOOK.md` §4 (rename "Three config traps" → four; add the reconciliation)
- Modify: `RUNBOOK.md` §8 (split the guest-join test)
- Modify: `docs/PLAN_2026-07-22.md:40` (stale line reference)

**Interfaces:**
- Produces: the corrected §8 checklist consumed by Phase I.

- [ ] **Step 1: Confirm both claims against current source**

```bash
curl -s https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/src/backend/meet/settings.py \
  | grep -n -A2 "ALLOW_UNREGISTERED_ROOMS = values"
curl -s https://raw.githubusercontent.com/suitenumerique/meet/refs/heads/main/env.d/production.dist/common \
  | grep -n "ALLOW_UNREGISTERED_ROOMS"
```

Expected: settings default `True` at ~`:665`; env template `ALLOW_UNREGISTERED_ROOMS=False` at `:50`. Both true; the env file wins.

- [ ] **Step 2: Retitle and extend the traps section**

In `RUNBOOK.md` §4, change the heading `### Three config traps` to `### Four config traps`, and insert as trap 1 (renumbering the rest):

```markdown
**1. `ALLOW_UNREGISTERED_ROOMS` — two true statements that look contradictory.**
The **code** default is `True` (`settings.py:665`). The **production env template**
ships `False` (`env.d/production.dist/common:50`). Both are correct; the env file
wins, so a stock deploy requires an account merely to *join* a call. Set `True`.

What the flag actually does (`core/api/viewsets.py:257-277`): it fires only when
`RoomViewSet.retrieve` raises `Http404` — a slug **not in the database**. It then
returns a synthetic public room plus a LiveKit token. It grants *ad-hoc rooms
conjured from a URL*. It has no effect on rooms that already exist.
```

- [ ] **Step 3: Split the smoke test in §8**

Replace this line:

```markdown
- [ ] **Open the room link in a private window — joins with no account** (validates `ALLOW_UNREGISTERED_ROOMS`)
```

with:

```markdown
- [ ] Open a **created** room's link in a private window — joins with no account
      *(validates room `access_level` + `RoomPermissions` — NOT the flag)*
- [ ] Open a slug that was **never created**, e.g. `/zzz-test-unregistered-2026`,
      in a private window — a room materialises and joins
      *(this, and only this, validates `ALLOW_UNREGISTERED_ROOMS`)*
```

- [ ] **Step 4: Fix the stale reference in the strategy doc**

In `docs/PLAN_2026-07-22.md:40`, replace `(default, src/backend/meet/settings.py:596)` with `(code default; the production env template overrides it to False — see RUNBOOK §4 trap 1)`.

- [ ] **Step 5: Verify**

```bash
grep -n "Four config traps" RUNBOOK.md && grep -c "never created" RUNBOOK.md
```

Expected: the heading matches, and `never created` appears once.

- [ ] **Step 6: Commit**

```bash
git add RUNBOOK.md docs/PLAN_2026-07-22.md
git commit -m "Document ALLOW_UNREGISTERED_ROOMS as the fourth trap; the old guest-join test never exercised it"
```

---

## Phase B — Preflight gates

> **Every task below is blocked on inputs this session does not have.** Nothing in Phases C–J can start until B1 closes.

### Task B1: Close the input gaps

**Blocking — cannot proceed without these:**

| # | Input | Why it blocks | Who |
|---|---|---|---|
| B1.1 | **Server IP** | Given as the literal placeholder `<IP>`. No host to reach. | Owner |
| B1.2 | **SSH access** | No key, user, or port. No way to execute anything. | Owner |
| B1.3 | **Clerk `OIDC_RP_CLIENT_ID` + secret** | Stated "ready to paste"; not supplied. Secret is unrecoverable if lost. | Owner → gitignored file only |
| B1.4 | **Resend API key** | Invitation emails silently fail without it. | Owner → gitignored file only |
| B1.5 | **Clerk redirect URI registered** | Must be exactly `https://visio.samourai.app/api/v1.0/callback/`. Verified: `core/urls.py` mounts `lasuite.oidc_login.urls` under `api/{API_VERSION}/`, `API_VERSION="v1.0"`, and `mozilla_django_oidc.urls` defines `callback/`. | Owner |
| B1.6 | **Clerk scopes** | Must include `openid`, `email`, **`profile`**. Without `profile`, names arrive empty regardless of any env var. | Owner |

**Decisions required — the plan branches on these:**

| # | Decision | Recommendation |
|---|---|---|
| B1.7 | **TURN / restrictive networks** (R12) — there is no TURN server. §8's "proves TURN over 443 works" cannot pass as written. | **Ship v1 without TURN**, rely on LiveKit ICE/TCP on 7881, and correct the runbook's claim. Revisit with a second Scaleway flexible IP dedicated to TURN/TLS on 443 — 443/tcp on the primary IP belongs to nginx-proxy and cannot be shared. |
| B1.8 | **Shared-org blast radius** (R10) — every `*.samourai.app` account can create rooms day one; every Visio signup becomes a Samouraï account everywhere. | Explicit go/no-go from the owner **plus** a CGU clause, before any promotion. |
| B1.9 | **LiveKit UDP port range** (R11) — upstream recommends a range ≥ vCPU count; `udp_port` and `port_range_*` are mutually exclusive, and a range needs firewall changes not in the currently-open set. | Launch on the single port. Move to a range only with a measured reason, since it widens the firewall. |

- [ ] **Step 1: Collect B1.1–B1.6 and record decisions B1.7–B1.9 in this file.**
- [ ] **Step 2: Confirm secrets are written only to `deploy/.env`, `deploy/env.d/common`, `deploy/env.d/postgresql` — all gitignored.**

```bash
git check-ignore -v deploy/.env deploy/env.d/common deploy/env.d/postgresql
```

Expected: three lines, each naming the `.gitignore` rule that covers it. Any file not listed is a leak risk — stop.

---

## Phase C — Host bootstrap

### Task C1: Verify the host and DNS

**Interfaces:**
- Consumes: B1.1 (IP), B1.2 (SSH).
- Produces: a reachable Docker host with correct DNS, consumed by every later phase.

- [ ] **Step 1: Confirm DNS resolves to the instance**

```bash
dig +short visio.samourai.app A; dig +short livekit.samourai.app A
```

Expected: both return the same IP from B1.1. Anything else — TLS issuance in Task E2 will fail.

- [ ] **Step 2: Confirm SSH and Docker Compose v2**

```bash
ssh "$VISIO_HOST" 'docker --version && docker compose version && nproc && free -g | head -2'
```

Expected: Compose **v2.x** (v1 has different `env_file` semantics — see Task D4), ≥4 vCPU, ≥16 GB RAM per RUNBOOK §2.

- [ ] **Step 3: Confirm the firewall matches the runbook**

```bash
ssh "$VISIO_HOST" 'sudo ufw status verbose'
```

Expected: 80/tcp, 443/tcp, 443/udp, 7881/tcp, 7882/udp. Note 443/udp will carry no traffic until decision B1.7 is revisited.

- [ ] **Step 4: Record the measured egress bandwidth cap**

```bash
ssh "$VISIO_HOST" 'cat /sys/class/net/$(ip route show default | awk "{print \$5}" | head -1)/speed 2>/dev/null || echo "unreported — check the Scaleway instance spec"'
```

RUNBOOK §2: bandwidth, not CPU, is what bites first. Write the number into §9 before promotion.

---

## Phase D — Configuration assembly

### Task D1: Fetch upstream artefacts verbatim

**Files:**
- Create on host: `~/visio/{compose.yaml,.env,livekit-server.yaml,default.conf.template}`, `~/visio/env.d/{common,postgresql}`

- [ ] **Step 1: Run RUNBOOK §3 unchanged**, then record the exact commit fetched:

```bash
curl -s https://api.github.com/repos/suitenumerique/meet/commits/main | grep -m1 '"sha"'
```

Write it into the runbook. Upgrades (§10) diff against this.

- [ ] **Step 2: Confirm the fetch matches what this plan was written against**

```bash
grep -c "ALLOW_UNREGISTERED_ROOMS=False" env.d/common   # expect 1
grep -c "OIDC_OP_LOGOUT_ENDPOINT"        env.d/common   # expect 1 — must NOT survive Task D2
grep -c "image: lasuite/meet-backend:latest" compose.yaml  # expect 1 — pinned in Task D3
```

If any count differs, upstream moved after 2026-07-22. **Stop and re-run the drift diff** before continuing.

---

### Task D2: Write the Clerk config

**Files:**
- Create on host: `~/visio/env.d/common` (from `deploy/env.d/common.example`, post-Task-A1)
- Create on host: `~/visio/env.d/postgresql`, `~/visio/.env`

**Interfaces:**
- Consumes: B1.3 (Clerk creds), B1.4 (Resend key), Task A1 (`FRONTEND_CUSTOM_CSS_URL`).

- [ ] **Step 1: Generate the three secrets** — RUNBOOK §3, unchanged.
- [ ] **Step 2: Copy the corrected templates and fill every placeholder.**
- [ ] **Step 3: Assert no placeholder survives**

```bash
grep -n "<.*>" env.d/common env.d/postgresql .env
```

Expected: no output. A surviving `<from Clerk dashboard>` boots a stack that fails only at the login click.

- [ ] **Step 4: Assert the Keycloak logout endpoint did not survive**

```bash
grep -n "OIDC_OP_LOGOUT_ENDPOINT\|KEYCLOAK\|REALM_NAME" env.d/common .env
```

Expected: no output. See DRIFT_REPORT Trap 3.

- [ ] **Step 5: Assert file permissions**

```bash
chmod 600 env.d/common env.d/postgresql .env && ls -l env.d/ .env
```

Expected: `-rw-------`.

---

### Task D3: Create `compose.override.yaml` — all our deltas in one file

**Files:**
- Create on host: `~/visio/compose.override.yaml`
- Create on host: `~/visio/custom/` ← `theme/custom.css` as `style.css`, plus `logo.png`

**Interfaces:**
- Produces: pinned images (R7), the CSS mount (BLOCKER-3), Redis persistence (R2), and the proxy wiring (RUNBOOK §5) — without editing upstream `compose.yaml`.

> **Why an override file.** RUNBOOK §5 says to edit `compose.yaml` in place, but §10 re-fetches it on every upgrade, silently discarding those edits. Compose loads `compose.yaml` + `compose.override.yaml` together by default; list keys (`volumes`, `networks`, `environment`) merge additively and scalars (`image`) replace. Upstream stays pristine and diffable.

- [ ] **Step 1: Stage the branding assets**

```bash
mkdir -p ~/visio/custom
# copy theme/custom.css from this repo to ~/visio/custom/style.css
# copy the Samouraï logo to ~/visio/custom/logo.png
ls -l ~/visio/custom/
```

Expected: `style.css` and `logo.png` both present and non-empty. `DJANGO_EMAIL_LOGO_IMG` points at `logo.png`; without it every invitation email ships a broken image.

- [ ] **Step 2: Write `compose.override.yaml`**

```yaml
# All visio.samourai.app deltas. Upstream compose.yaml stays untouched so it
# can be re-fetched verbatim at upgrade time (RUNBOOK §10).
services:
  postgresql:
    image: postgres:16

  redis:
    # R2: upstream ships redis:5 (long EOL) with no volume. Sessions are
    # cache-backed (SESSION_ENGINE=...backends.cache -> redis://redis:6379/1),
    # so an unpersisted Redis logs out every user on every restart.
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - ./data/redis:/data

  backend:
    image: lasuite/meet-backend:v1.24.0

  frontend:
    image: lasuite/meet-frontend:v1.24.0
    environment:
      - VIRTUAL_HOST=${MEET_HOST}
      - VIRTUAL_PORT=8083
      - LETSENCRYPT_HOST=${MEET_HOST}
    volumes:
      # BLOCKER-3: serves FRONTEND_CUSTOM_CSS_URL=/custom/style.css and
      # DJANGO_EMAIL_LOGO_IMG=.../custom/logo.png. Without this both 404.
      - ./custom:/usr/share/nginx/html/custom:ro
    networks:
      - proxy-tier
      - default

  livekit:
    image: livekit/livekit-server:v1.13.4
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

- [ ] **Step 3: Verify the merge produces what you expect — before starting anything**

```bash
cd ~/visio && docker compose config | grep -E "image:|/custom|appendonly"
```

Expected: three pinned `lasuite/*` and `livekit/*` tags, **no `:latest` anywhere**, the `./custom` mount on `frontend`, and `--appendonly yes` on `redis`.

- [ ] **Step 4: Assert no `latest` survives**

```bash
docker compose config | grep -c "latest"
```

Expected: `0`.

---

### Task D4: Settle `env_file` interpolation (R6) — before anything starts

> Upstream's own template puts `${MEET_HOST}` **inside** `env.d/common`, which is loaded via `env_file:`. Compose's substitution rules for `env_file` values have changed across versions. If it does not interpolate, `DJANGO_ALLOWED_HOSTS` becomes the literal string `${MEET_HOST}` and **every request returns 400**. This is a five-minute check that prevents an hour of misdirected debugging.

- [ ] **Step 1: Ask Compose what the container will actually receive**

```bash
cd ~/visio && docker compose config | grep -E "DJANGO_ALLOWED_HOSTS|MEET_BASE_URL|LIVEKIT_API_URL"
```

Expected (good): `visio.samourai.app`, `https://visio.samourai.app`, `https://livekit.samourai.app`.
Failure signal: a literal `${MEET_HOST}` anywhere.

- [ ] **Step 2: Confirm at runtime, not just in config**

```bash
docker compose run --rm backend printenv DJANGO_ALLOWED_HOSTS MEET_BASE_URL
```

Expected: fully expanded values.

- [ ] **Step 3: If interpolation did not happen**, hard-code the literal hostnames in `env.d/common` (`DJANGO_ALLOWED_HOSTS=visio.samourai.app`, `MEET_BASE_URL="https://visio.samourai.app"`, `LIVEKIT_API_URL=https://livekit.samourai.app`, `OIDC_REDIRECT_ALLOWED_HOSTS=["https://visio.samourai.app"]`) and re-run Step 2 to confirm.

---

## Phase E — Reverse proxy, TLS, launch

### Task E1: Stand up nginx-proxy

- [ ] **Step 1:** `docker network create proxy-tier`
- [ ] **Step 2:** Deploy the upstream nginx-proxy example (`docs/examples/compose/nginx-proxy/compose.yaml`, confirmed present today).
- [ ] **Step 3: Verify it holds 80 and 443**

```bash
ssh "$VISIO_HOST" 'sudo ss -tlnp | grep -E ":80 |:443 "'
```

Expected: both bound by the proxy. This is also why TURN/TLS cannot have 443/tcp (decision B1.7).

### Task E2: Launch and migrate

- [ ] **Step 1:** `docker compose up -d`
- [ ] **Step 2: Wait for the backend healthcheck** (upstream: `python manage.py check`, 15s interval, 20 retries)

```bash
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
```

Expected: `backend` reports `healthy`. If it never does — `docker compose logs backend` — the usual causes are Task D4 (interpolation) and a surviving `<placeholder>` from Task D2.

- [ ] **Step 3:** `docker compose run --rm backend python manage.py migrate`
- [ ] **Step 4:** `docker compose run --rm backend python manage.py createsuperuser --email <owner address>`
- [ ] **Step 5: Verify TLS on both hosts**

```bash
curl -sSI https://visio.samourai.app    | head -1
curl -sSI https://livekit.samourai.app  | head -1
```

Expected: HTTP 200/302 on both, no certificate error.

### Task E3: Prove `X-Forwarded-Proto` survives the two-hop proxy (R1)

> Production sets `SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")` and `SECURE_SSL_REDIRECT=True`. The inner `default.conf.template` sets only `Host` and `X-Forwarded-For`. The chain works **only** if nginx-proxy injects the header and the inner nginx passes it through. If it doesn't: infinite redirect loop, and OIDC builds `http://` redirect URIs that Clerk rejects. Test it before touching login.

- [ ] **Step 1: Look for a redirect loop**

```bash
curl -sS -o /dev/null -w "%{http_code} %{num_redirects} -> %{url_effective}\n" -L https://visio.samourai.app/
```

Expected: `200 0` or a single redirect terminating on `https://`. A climbing redirect count, or any `http://` in `url_effective`, means the header is not arriving.

- [ ] **Step 2: Ask Django directly**

```bash
docker compose exec backend python -c "
import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','meet.settings')
from configurations import importer; importer.install(); django.setup()
from django.conf import settings
print('proxy header:', settings.SECURE_PROXY_SSL_HEADER)
print('ssl redirect:', settings.SECURE_SSL_REDIRECT)
print('allowed hosts:', settings.ALLOWED_HOSTS)
print('csrf trusted:', settings.CSRF_TRUSTED_ORIGINS)"
```

Expected: `('HTTP_X_FORWARDED_PROTO','https')`, `True`, `['visio.samourai.app']`, and a CSRF list that is empty (acceptable) — see Step 3.

- [ ] **Step 3: If Step 1 loops**, add to `env.d/common` and restart:

```env
DJANGO_CSRF_TRUSTED_ORIGINS=["https://visio.samourai.app"]
```

and add `proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;` to both `location @proxy_to_meet_*` blocks in `default.conf.template`. Re-run Step 1.

---

## Phase F — Identity gauntlet

### Task F1: Prove the Clerk round-trip

**Interfaces:** Consumes B1.3, B1.5, B1.6, Task E3.

- [ ] **Step 1: Confirm Clerk still advertises what §1 recorded**

```bash
curl -s https://clerk.samourai.app/.well-known/openid-configuration \
  | python3 -m json.tool | grep -E "issuer|authorization_endpoint|token_endpoint|userinfo_endpoint|jwks_uri|code_challenge|id_token_signing"
```

Expected: matches RUNBOOK §1 exactly. Any drift → re-derive `env.d/common` before proceeding.

- [ ] **Step 2: Log in through the browser.** Expect Clerk, then a return to Meet.
- [ ] **Step 3: Assert the user record is complete — this is traps 1 and 2**

```bash
docker compose run --rm backend python manage.py shell -c "
from core.models import User
u = User.objects.order_by('-id').first()
print(repr(u.email), repr(u.full_name), repr(u.short_name))"
```

Expected: real email, real full name, real short name.
- Empty `full_name` → `profile` scope missing (trap 2, B1.6) **or** `OIDC_USERINFO_FULLNAME_FIELDS` not applied (trap 1).
- `None` values → check `OIDC_CREATE_USER=true`.

- [ ] **Step 4: If login fails, apply the R5 fallback.** We enable `OIDC_USE_PKCE=true` (upstream default `False`) while also sending a client secret. Clerk advertises `S256`, and mozilla-django-oidc supports the pairing, but it is unproven here. Set `OIDC_USE_PKCE=false`, restart the backend, retry. Record which setting worked.

- [ ] **Step 5: Confirm logout degrades exactly as documented (trap 3).**
Click log out → lands on `LOGOUT_REDIRECT_URL`, no 500. Click log in → **silently re-authenticates without a Clerk prompt**. That is correct and expected: `views.py:89-92` returns the plain redirect URL and `auth.logout()` clears only the Django session. Confirm the behaviour is acceptable to the owner (B1.8) rather than treating it as a bug.

---

## Phase G — Media path

### Task G1: Prove LiveKit is reachable and speaks `wss://` (R4)

- [ ] **Step 1: Confirm the signalling endpoint answers over TLS**

```bash
curl -sSI https://livekit.samourai.app | head -1
```

- [ ] **Step 2: Inspect what the frontend is told to connect to**

```bash
curl -s https://visio.samourai.app/api/v1.0/config/ | python3 -m json.tool | grep -i livekit
```

- [ ] **Step 3: Open a room and read the browser console.** Expected: a `wss://livekit.samourai.app` websocket that stays open.
- [ ] **Step 4: If the client attempts `https://` and fails**, set `LIVEKIT_FORCE_WSS_PROTOCOL=true` in `env.d/common`, restart the backend, retry.
- [ ] **Step 5: Confirm ICE ports are actually reachable from outside**

```bash
nc -zv <IP> 7881          # ICE/TCP
nc -zuv <IP> 7882         # WebRTC/UDP
```

Both must succeed. 7881 is the only fallback restrictive networks get, given decision B1.7.

---

## Phase H — Branding

### Task H1: Prove the CSS is actually served

- [ ] **Step 1:**

```bash
curl -sS -o /dev/null -w "%{http_code} %{content_type}\n" https://visio.samourai.app/custom/style.css
```

Expected: `200 text/css`. A 404 means the Task D3 mount is missing (BLOCKER-3).

### Task H2: Prove the backend advertises it

- [ ] **Step 1:**

```bash
curl -s https://visio.samourai.app/api/v1.0/config/ | python3 -m json.tool | grep -i css
```

Expected: `"custom_css_url": "/custom/style.css"`. Absent or `null` → the env var name is wrong (BLOCKER-1) or the backend wasn't restarted.

### Task H3: Reconcile tokens against the live DOM

> Tasks H1 and H2 prove the file is *delivered*. Only this task proves it *applies*. The audit in the drift report was done against `panda.config.ts` at `main`; the running image is `v1.24.0`, so a residual mismatch is possible.

- [ ] **Step 1: Enumerate the tokens the running app actually defines**

In devtools on `https://visio.samourai.app`:

```js
[...document.styleSheets].flatMap(s => { try { return [...s.cssRules] } catch { return [] } })
  .filter(r => r.style)
  .flatMap(r => [...r.style].filter(p => p.startsWith('--colors-') || p.startsWith('--fonts-')))
  .filter((v, i, a) => a.indexOf(v) === i).sort()
```

- [ ] **Step 2: Confirm the override landed**

```js
getComputedStyle(document.documentElement).getPropertyValue('--colors-primary').trim()
```

Expected: `#FD6262`. Anything else → the token name is wrong; correct `theme/custom.css` against Step 1's list and re-run.

- [ ] **Step 3: Check the in-room palette separately.** Join a room and re-run Step 2 for `--colors-primary-dark-500`. Meet has no light/dark toggle — light outside, dark inside — so the two surfaces must be verified independently.
- [ ] **Step 4: Commit any correction back to `theme/custom.css` with the live-DOM evidence in the message.**

### Task H4: Attribution

- [ ] **Step 1:** Confirm "Propulsé par La Suite Meet", linking to `github.com/suitenumerique/meet`, is visible in the deployed UI.
- [ ] **Step 2:** Note the constraint honestly — `theming.md` states the footer is not yet customisable, and the browser-tab name needs the `VITE_APP_TITLE` **build arg**, i.e. a rebuilt frontend image. That contradicts the repo's "no fork" position. **Recommendation: accept the upstream tab title for v1.** Rebuilding for a browser-tab string means owning an image, a build pipeline, and an upgrade burden — a poor trade this early.

---

## Phase I — Smoke tests (supersedes RUNBOOK §8)

- [ ] **I1** `https://visio.samourai.app` loads over TLS
- [ ] **I2** Log in → Clerk → back to Meet, **name and email correct** *(traps 1 + 2 — Task F1 Step 3)*
- [ ] **I3** Create a room as a logged-in user
- [ ] **I4** Open the **created** room's link in a private window — joins with no account *(validates `access_level` + `RoomPermissions`)*
- [ ] **I5** Open a slug **never created** — e.g. `/zzz-test-unregistered-2026` — in a private window; a room materialises and joins *(**this alone** validates `ALLOW_UNREGISTERED_ROOMS` — see DRIFT_REPORT Trap 4 Correction B)*
- [ ] **I6** Custom CSS applied — verified in the DOM, not merely served *(Task H3)*
- [ ] **I7** 3-way call: audio, video, screenshare
- [ ] **I8** Mobile browsers: iOS Safari + Android Chrome
- [ ] **I9** Restrictive network (mobile data / corporate VPN). ⚠️ **Rewritten:** the old wording claimed this "proves TURN over 443 works". There is no TURN server (R12). This test measures how far ICE/TCP on 7881 gets us. **Record the result; do not treat failure as a blocker unless decision B1.7 changes.**
- [ ] **I10** Invitation email arrives via Resend, **and its logo renders** *(needs the Task D3 mount)*
- [ ] **I11** `/admin` reachable; non-admins rejected
- [ ] **I12** Restart Redis, confirm the session behaviour matches expectation *(R2)*

```bash
docker compose restart redis && sleep 5 && curl -sSI https://visio.samourai.app | head -1
```

Reload the browser: you should still be logged in **because** Task D3 added `--appendonly yes` + a volume. If you are logged out, persistence did not take.

---

## Phase J — Before promotion (supersedes RUNBOOK §9)

- [ ] **J1** Retention policy — monthly reset of rooms/accounts, matching `visio.lasuite.coop`. Must explicitly cover the Clerk ID tokens held in Redis sessions (R9).
- [ ] **J2** Caps — max participants per room, max room duration.
- [ ] **J3** CGU + abuse contact published, **including the shared-org clause** (R10/B1.8): a Visio signup creates a Samouraï account across every `*.samourai.app` product.
- [ ] **J4** Backups — `pg_dump` on cron, off-box, **restore-tested at least once**. An untested backup is not a backup.
- [ ] **J5** Monitoring — Sentry (`sentry.samourai.pro`) + uptime + a bandwidth alert set at the Task C1 Step 4 number.
- [ ] **J6** Bandwidth ceiling — the number at which you throttle or pay, decided in advance.
- [ ] **J7** Load measurement at 10 / 50 / 200 concurrent participants (RUNBOOK §2). Costs in `docs/PLAN_2026-07-22.md:85` are flagged unvalidated; validate before promising a free service.
- [ ] **J8** Record the pinned versions and the upstream commit from Task D1 Step 1, so §10 upgrades have a baseline to diff.

---

## Self-review

**Spec coverage.** The five items requested map as follows: *(1) RUNBOOK §3–§6* → Phases D, E; *(2) upstream drift diff* → done, DRIFT_REPORT Part 1, folded into Tasks A1–A3 and D1; *(3) four traps verified* → DRIFT_REPORT Part 3, all four confirmed against current source, enforced by Tasks A3, D2, F1; *(4) §8 smoke tests incl. guest-join* → Phase I, with I5 corrected because the original test never exercised the flag; *(5) theme reconciliation* → Tasks A2 and H3, with the DOM check that turns "indicative" into "verified".

**Known gaps, stated rather than hidden.**
- Phases C–J are unexecuted and unexecutable until B1 closes.
- Task H3 cannot be completed without a running app; the offline half (A2) is done and evidence-backed, the online half is specified and pending.
- R12 (no TURN) is a decision, not a task. It is the one finding that changes what the product can promise.

**Placeholder scan.** No `TBD` / `implement later` / "add error handling" steps. Every code and config block is complete and pasteable. `<IP>`, `<owner address>`, and the Clerk/Resend credentials are genuine external inputs, all enumerated in B1 with an owner.
