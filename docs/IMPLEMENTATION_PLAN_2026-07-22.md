# visio.samourai.app — Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Status: PROPOSAL, REVISED AFTER EXPERT REVIEW — awaiting owner review. Nothing in Phases B–J has been executed.**
> Evidence base: [DRIFT_REPORT_2026-07-22.md](DRIFT_REPORT_2026-07-22.md).
> **Corrections: [CTO_REVIEW_2026-07-22.md](CTO_REVIEW_2026-07-22.md) — read this second and treat it as authoritative where it disagrees with anything below.** Four independent expert reviews found one defect that would have broken authentication outright, one that would have shipped an inaccessible interface, and four verification steps that would have reported success while the system was broken. The critical fixes are applied below; the review carries the full reasoning and the items still outstanding.

**Goal:** Bring La Suite Meet live at `visio.samourai.app`, authenticated against the existing Clerk org, with working guest-join, working branding, and an honest account of what does and does not work on restrictive networks.

**Architecture:** Single Scaleway host. Docker Compose, five services (PostgreSQL, Redis, LiveKit, Meet backend, Meet frontend) behind nginx-proxy with Let's Encrypt. Clerk is the external OIDC provider — no Keycloak. All of our deltas live in `compose.override.yaml` so upstream's `compose.yaml` stays pristine and re-fetchable at upgrade time. No fork of the application.

**Tech Stack:** Docker Compose v2, Django 5 (`django-configurations`), `django-lasuite` + `mozilla-django-oidc`, LiveKit SFU, PostgreSQL 16, Redis, Panda CSS (frontend design tokens), nginx-proxy + acme-companion.

---

## Global Constraints

- **Never commit to `main`/`master`.** Feature branches + PR only. No Claude attribution in commits, PR bodies, tags, or release notes.
- **Secrets live only in gitignored files.** Tracked files carry `*.example` placeholders and nothing else. The Clerk client secret is displayed once and is unrecoverable.
- **List-valued env vars are COMMA-SEPARATED, never JSON.** `values.ListValue` parses with `value.strip().split(',')` (`django-configurations configurations/values.py:238`) — it never parses JSON. `["a","b"]` becomes `['["a"', '"b"]']` and silently breaks. Write `a,b`. Applies to `OIDC_USERINFO_FULLNAME_FIELDS`, `OIDC_REDIRECT_ALLOWED_HOSTS`, `OIDC_USERINFO_ESSENTIAL_CLAIMS`, `DJANGO_CSRF_TRUSTED_ORIGINS`. **Upstream's own template gets this wrong.**
- **Never run bare `docker compose config`.** It expands `env_file` and prints every secret to stdout. Use `--no-env-resolution` for structure, `--images` for tags, and a filtered `--format json` selection when resolved values are genuinely needed.
- **`FRONTEND_CUSTOM_CSS_URL`** is the correct variable name. `FRONTEND_CSS_URL` does not exist.
- **Design tokens are Panda CSS** (`--colors-*`, `--fonts-*`). Cunningham `--c--theme--*` names are dead. Override the **palette ramp** (`--colors-primary-800`, `--colors-primary-dark-100`), not only the semantic tier — the app paints its most visible surfaces from the ramp.
- **Every brand colour must clear WCAG AA (4.5:1) for text and 3:1 for UI.** `#FD6262` on white is 2.96:1 and `#889CE7` on white is 2.64:1 — neither may carry white text or serve as a focus ring.
- **Assert on command output, never on grep exit codes** — implementations differ (`ugrep` exits 2 where GNU grep exits 1).
- **Pin every image tag.** No `latest` reaches the host.
- **Upstream `compose.yaml` is read-only**, re-fetched verbatim at upgrade. Our changes go in `compose.override.yaml`.
- **Verify-first.** Infrastructure has no unit tests, so every task states its check, runs it *before* the change to observe the failure, then runs it again to observe the pass. A task without an executed check is not done.
- **Attribution stays visible.** "Propulsé par La Suite Meet" with a link to `suitenumerique/meet` must survive every theme change.
- Target versions as of 2026-07-22: `lasuite/meet-backend:v1.24.0`, `lasuite/meet-frontend:v1.24.0`, `livekit/livekit-server:v1.13.4`, `postgres:16`, `redis:7-alpine`.

---

## Phase A — Repository corrections (no server required)

> These tasks fix defects that exist in the repo *today*. They need no IP, no credentials, and no host. They can land before any infrastructure work and should, because they are what makes Phases F and H succeed on the first attempt.

### Task A0: Fix the list-value syntax — authentication is broken without this

**Files:**
- Modify: `deploy/env.d/common.example:45,52`
- Modify: `RUNBOOK.md:185,192`

**Interfaces:**
- Produces: parseable OIDC list settings, consumed by Tasks D2 and F1.

> **This is the single most consequential fix in the plan.** Trap 1 was correctly identified in the runbook and then fixed in a syntax django-configurations cannot parse, so display names would still be empty — and the plan's own diagnostic pointed at the wrong cause. See [CTO_REVIEW §1.1](CTO_REVIEW_2026-07-22.md).

- [ ] **Step 1: Reproduce the defect — no server needed**

```bash
python3 -c "
for v in ['[\"given_name\",\"family_name\"]', 'given_name,family_name']:
    print(f'{v!r:34} -> ' + str(list(filter(None,[x.strip() for x in v.strip().split(\",\")]))))"
```

Expected output — the first line is what the repo ships today:

```
'["given_name","family_name"]'     -> ['["given_name"', '"family_name"]']
'given_name,family_name'           -> ['given_name', 'family_name']
```

- [ ] **Step 2: Correct `deploy/env.d/common.example`**

Replace lines 45 and 52:

```env
# Comma-separated. NOT JSON — values.ListValue splits on ',' and never parses
# JSON (django-configurations configurations/values.py:238). Brackets and quotes
# become part of the field names and every display name silently renders empty.
OIDC_USERINFO_FULLNAME_FIELDS=given_name,family_name
OIDC_USERINFO_SHORTNAME_FIELD=given_name
# Requires `email` in userinfo. Default is [] which demands only `sub`, so a Clerk
# identity with no email would create a silent null-email account.
OIDC_USERINFO_ESSENTIAL_CLAIMS=email
```

```env
# Host only — no scheme, no brackets. Django compares urlparse(url).netloc
# against this set, so a scheme-bearing entry can never match.
OIDC_REDIRECT_ALLOWED_HOSTS=visio.samourai.app
```

- [ ] **Step 3: Apply the same correction to `RUNBOOK.md:185,192`.**

- [ ] **Step 4: Verify no bracketed list survives**

```bash
grep -nE '^[A-Z_]+=\[' deploy/env.d/common.example RUNBOOK.md
```

Expected: no output. (Assert on the output, not the exit code.)

- [ ] **Step 5: Commit**

```bash
git add deploy/env.d/common.example RUNBOOK.md
git commit -m "Use comma-separated OIDC list values — JSON syntax silently breaks every display name"
```

### Task A1: Correct the CSS variable name

**Files:**
- Modify: `deploy/env.d/common.example:67`
- Modify: `RUNBOOK.md:207`, `RUNBOOK.md:279`
- Modify: `README.md:33`, `README.md:40` ← *missed in the first draft; the repo's front door carries the wrong name*
- Modify: `docs/PLAN_2026-07-22.md:68`, `docs/PLAN_2026-07-22.md:97`

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

`docs/` is excluded because the analysis documents legitimately quote the wrong name; without that the check can never go green.

```bash
grep -rn "FRONTEND_CSS_URL" . --exclude-dir=.git --exclude-dir=docs
grep -c "FRONTEND_CUSTOM_CSS_URL" deploy/env.d/common.example RUNBOOK.md README.md
```

Expected: **no output** from the first command (assert on output, not exit code — `ugrep` exits 2 where GNU grep exits 1). Non-zero counts from the second.

- [ ] **Step 5: Commit**

```bash
git add deploy/env.d/common.example RUNBOOK.md README.md docs/PLAN_2026-07-22.md
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

> Ramp values below were derived by reproducing Panda's codegen locally against `v1.24.0` with the pinned compiler, then validated numerically against the actual component pairings. Contrast ratios in the comments are measured, not estimated.

```css
/* ─────────────────────────────────────────────────────────────
   Samouraï Visio — runtime theme over La Suite Meet v1.24.0
   Loaded via FRONTEND_CUSTOM_CSS_URL (a BACKEND setting) ->
   /api/v1.0/config/ -> AppInitialization.tsx appends <link> to <head>.

   Token authority: the CSS emitted by @pandacss/dev from
   src/frontend/panda.config.ts. No prefix is configured, so vars are
   --colors-* / --fonts-*, camelCase kebab-cased
   (primaryDark -> --colors-primary-dark-*, focusRing -> --colors-focus-ring).

   CRITICAL: the app reads the PALETTE ramp far more than the semantic tier.
   buttonRecipe.ts:56 uses primary.800 with a LITERAL `white`, not primary.text.
   Overriding only --colors-primary leaves every button Bleu France.

   No !important: an unlayered :root already beats Panda's @layer tokens, and
   !important would break the html.font-lexend accessibility override.
   ───────────────────────────────────────────────────────────── */

@import url('https://fonts.bunny.net/css?family=inter:400,500,600,700&display=swap');

:root {
  /* ── LIGHT SURFACE (outside a room) — palette ramp ──
     Brand coral #FD6262 is 2.96:1 on white: it CANNOT carry white text.
     It stays at .500 (decorative) while the text/fill steps darken. */
  --colors-primary-50:   #FFF6F6;
  --colors-primary-100:  #FEECEC;   /* tertiary button bg */
  --colors-primary-200:  #FDE2E2;   /* LoginHint bg — ink 14.8:1 */
  --colors-primary-300:  #FBD5D5;   /* tertiary hover bg */
  --colors-primary-400:  #F58A8A;   /* disabled text only (WCAG-exempt) */
  --colors-primary-500:  #FD6262;   /* Kodera coral, decorative */
  --colors-primary-600:  #A63A3A;   /* focus box-shadow ring */
  --colors-primary-700:  #8F2E2E;
  --colors-primary-800:  #B83636;   /* PRIMARY BUTTON FILL + link/border text (20 usages)
                                       white on it 5.80:1 AA · on white 5.80:1 AA */
  --colors-primary-900:  #8F2E2E;   /* tertiaryText — 8.08:1 on white */
  --colors-primary-950:  #5C1E1E;
  --colors-primary-action: #A63A3A; /* primary button hover — 6.39:1 AA */

  /* ── LIGHT SURFACE — semantic tier ──
     Also feeds the LiveKit accent chain (livekit.css:14-18), so it must read
     on BOTH white and the #141416 room surface. */
  --colors-primary:             #CC4444;  /* white on it 4.69:1 AA · vs room bg 3.92:1 */
  --colors-primary-hover:       #B83636;  /* 5.80:1 AA */
  --colors-primary-active:      #A63A3A;  /* 6.39:1 AA */
  --colors-primary-text:        #FFFFFF;  /* forced white: paired with primary,
                                             primary.active, primary.800 AND
                                             primaryDark.100 — no ink suits all four */
  --colors-primary-subtle:      #FEECEC;
  --colors-primary-subtle-text: #8F2E2E;  /* Badge — 7.09:1 AA */

  /* ── DARK SURFACE (inside a room) ──
     Luminance-matched to upstream's ramp so every contrast relation the
     upstream designers built is preserved, rehued to Samouraï lavender.
     .100 is the workhorse (27 usages). .500 and .action have ZERO usages
     in v1.24.0 — set only for forward-compatibility.
     .700/.900 are INVERTED (light) selected states: darkening them breaks them. */
  --colors-primary-dark-50:     #141416;  /* Kodera bg — room canvas, white 18.4:1 */
  --colors-primary-dark-75:     #222429;
  --colors-primary-dark-100:    #2D3037;  /* buttons/tooltips/menus — white 13.2:1 */
  --colors-primary-dark-200:    #434655;
  --colors-primary-dark-300:    #585E75;  /* hover — white 6.42:1 */
  --colors-primary-dark-400:    #6B759C;
  --colors-primary-dark-500:    #889CE7;  /* Samouraï lavender (unused in 1.24.0) */
  --colors-primary-dark-600:    #96A2CC;
  --colors-primary-dark-700:    #ACB7DF;  /* inverted — .100 text on it 6.66:1 AA */
  --colors-primary-dark-800:    #C4CBE9;
  --colors-primary-dark-900:    #DCE1F2;  /* Select open — .100 text 10.13:1 AA */
  --colors-primary-dark-950:    #F4F5FB;

  /* ── Focus ring (index.css:39,47) — must clear 3:1 on white AND on #141416.
     Pure lavender #889CE7 is 2.64:1 on white and FAILS. Darkened. */
  --colors-focus-ring: #5C6FBF;   /* white 4.69:1 · room 3.93:1 */

  /* ── Type ── */
  --fonts-sans: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
}

/* Attribution. There is NO footer element: use_french_gov_footer defaults to
   false and Footer.tsx:125 returns null. The only stable hook upstream ships
   is .Header-beforeLogo (Header.tsx:153) — the same one DINUM uses. */
.Header-beforeLogo::after {
  content: 'Propulsé par La Suite Meet';
  display: block;
  font-size: 0.6875rem;
  line-height: 1;
  opacity: 0.7;
  margin-top: 0.25rem;
}
```

> **Lavender is not dropped — it is relocated.** Panda exposes no `secondary` semantic token, but upstream's `primaryDark` ramp *is* a lavender-indigo (default `.500` is `#8787D7`, within a hair of Samouraï's `#889CE7`). Rehueing the dark ramp is the correct home for it. It must not become the focus ring: `#889CE7` scores 2.64:1 on white and fails 1.4.11's 3:1 threshold.
>
> **`--colors-error` is not a token.** `panda.config.ts:171` defines an `error` *palette ramp* (`--colors-error-100…950`); the semantic destructive token at `:316` is `--colors-danger`. Upstream's `theming.md:57` is wrong, and the first draft of the drift report inherited that error.

- [ ] **Step 3: Update the runbook's starter block**

Replace the CSS block in `RUNBOOK.md` §7 with the `:root` block above, and replace the note *"Token names are indicative — confirm against the live DOM and `docs/theming.md`, since Cunningham's variable names drift between versions"* with:

```markdown
> Tokens are **Panda CSS** (`src/frontend/panda.config.ts`), not Cunningham.
> Meet has no light/dark toggle — light outside a meeting, dark in a room.
> Confirm every token against the live DOM before calling the theme done (§8).
```

- [ ] **Step 4: Verify no dead token survives, and no failing colour was introduced**

```bash
grep -rn --exclude-dir=.git --exclude-dir=docs -- "--c--theme--" .
python3 -c "
def rl(c):
    c=c.lstrip('#'); v=[int(c[i:i+2],16)/255 for i in (0,2,4)]
    v=[x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4 for x in v]
    return 0.2126*v[0]+0.7152*v[1]+0.0722*v[2]
def cr(a,b):
    l=sorted([rl(a),rl(b)],reverse=True); return (l[0]+0.05)/(l[1]+0.05)
for a,b,lbl,mn in [('#B83636','#FFFFFF','primary-800/white',4.5),('#CC4444','#FFFFFF','primary/white',4.5),
                   ('#5C6FBF','#FFFFFF','focus-ring/white',3.0),('#5C6FBF','#141416','focus-ring/room',3.0)]:
    r=cr(a,b); print(f'{lbl:22} {r:5.2f}:1  {\"PASS\" if r>=mn else \"FAIL\"}')"
```

Expected: **no output** from grep, and four `PASS` lines.

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
