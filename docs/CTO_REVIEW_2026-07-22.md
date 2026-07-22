# CTO Expert Review — Deployment Plan, 2026-07-22

> Four independent expert reviews of [IMPLEMENTATION_PLAN_2026-07-22.md](IMPLEMENTATION_PLAN_2026-07-22.md) and [DRIFT_REPORT_2026-07-22.md](DRIFT_REPORT_2026-07-22.md), reconciled. Reviewers worked in parallel with no knowledge of each other's findings, each briefed to assume the plan was wrong.
>
> **Outcome: the diagnosis held; the execution did not.** All three blockers and all four traps survived scrutiny. But one trap's *fix* was written in a syntax that silently does nothing, the proposed theme would have shipped an accessibility regression, and four verification steps could not detect the failures they existed to detect.

| Track | Scope |
|---|---|
| **A — Identity & security** | Clerk↔django-lasuite, OIDC, secrets, proxy trust |
| **B — Infrastructure & SRE** | Compose, TLS, LiveKit/WebRTC, capacity, durability |
| **C — Frontend & design systems** | Panda tokens, asset serving, accessibility |
| **D — Process red-team** | Falsifiability, rollback, legal, staging |

Tracks B and C went beyond reading: B settled every Compose claim empirically on v2.40.3; C fetched the `v1.24.0` tarball and **reproduced Panda's codegen locally** with the pinned compiler to obtain the authoritative CSS-variable list. Claims below marked ✅ were re-verified independently in the main session before acceptance.

---

## 1. Corrections to my own work — the honest list

These are findings against the plan and drift report I wrote. They are listed first because they matter most.

### 1.1 CRITICAL · Trap 1's fix does not work ✅ *verified in source*

`OIDC_USERINFO_FULLNAME_FIELDS=["given_name","family_name"]` — the value everyone has treated as the fix — **cannot parse**. It is a `values.ListValue`, and django-configurations parses those with a plain comma split, never JSON:

```python
# django-configurations configurations/values.py:238
split_value = [v.strip() for v in value.strip().split(self.separator)]   # separator = ','
```

Reproduced exactly:

```
'["given_name","family_name"]'  →  ['["given_name"', '"family_name"]']      ← broken
'given_name,family_name'        →  ['given_name', 'family_name']            ← correct
```

`user_info.get('["given_name"')` returns `None`, so `full_name` is `None` for **every user**. The trap was correctly identified in the runbook and then fixed in a syntax that silently does nothing.

My drift report verified that the *setting name and semantics* were right. It never checked that the *value would parse*. That is the gap.

Three compounding facts:
- Same defect on `OIDC_REDIRECT_ALLOWED_HOSTS` — inert, but it means the allowlist matches nothing and only `request.get_host()` is effective.
- **Upstream's own production template carries this bug** at `env.d/production.dist/common:44`.
- My Task E3 remediation, `DJANGO_CSRF_TRUSTED_ORIGINS=["https://…"]`, would fail Django system check `4_0.E001` → `manage.py check` errors → the backend healthcheck never goes healthy. My fix for one problem would have caused a worse one.

**Correction:** comma-separated, no brackets, no quotes.

```env
OIDC_USERINFO_FULLNAME_FIELDS=given_name,family_name
OIDC_REDIRECT_ALLOWED_HOSTS=visio.samourai.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://visio.samourai.app   # only if ever needed
```

Track A notes `OIDC_USERINFO_FULLNAME_FIELDS=name` is the lower-variance choice — a single token that cannot be mis-split, and Clerk returns `name` under the same `profile` scope.

### 1.2 CRITICAL · The proposed theme overrode the wrong layer and failed accessibility ✅ *contrast re-verified*

My Task A2 CSS used real token names — Track C confirmed all ten exist — but overrode the **semantic** tier while the app paints its most visible surfaces from the **palette** ramp:

```ts
// src/frontend/src/primitives/buttonRecipe.ts:55-64
primary: {
  backgroundColor: 'primary.800',   // → var(--colors-primary-800) = #000091 Bleu France
  color: 'white',                   // ← LITERAL, not primary.text
```

`primary.800` has **20 usages**; my CSS overrode none of them. Every primary button, secondary border, tab and switch would have stayed French-government blue. Likewise in-room: `primaryDark.100` has **27 usages** and I overrode `primaryDark.500` and `.action`, which have **zero usages in v1.24.0**. My dark-surface overrides were dead code.

And the palette itself fails WCAG. Measured, not estimated:

| Pair | Ratio | AA text (4.5) | Non-text (3.0) |
|---|---|---|---|
| `#FD6262` on white | **2.96:1** | ❌ | ❌ |
| `#889CE7` on white | **2.64:1** | ❌ | ❌ |
| upstream `#000091` on white | 14.91:1 | ✅ | ✅ |

Coral cannot be a white-text button fill — and `primary.text` is structurally forced to white because it is paired with `primary`, `primary.active`, `primary.800` **and** `primaryDark.100`; no single ink satisfies all four. So the fill must darken. Track C supplied a luminance-matched replacement ramp that keeps the brand and clears AA; it is adopted wholesale in the revised plan.

Two further corrections from the same track:
- **`--colors-error` does not exist.** ✅ Verified: `panda.config.ts:171` defines an `error` *palette ramp* (`--colors-error-100…950`); the *semantic* destructive token at `:316` is `--colors-danger`. My drift report's token table inherited this error from upstream's own `theming.md:57`.
- **`.samourai-credit` is dead CSS.** No element carries that class, and with `use_french_gov_footer=false` (the default) `Footer.tsx:125` returns `null` — there is no footer at all. My Global Constraint requiring visible attribution was unimplementable as written. The only stable hook upstream ships is `.Header-beforeLogo`, which exists precisely for deployer branding.

### 1.3 HIGH · Four verification steps could not detect their own failures

The plan's central discipline was "verify-first." Four checks fail that discipline:

| Step | Defect |
|---|---|
| **D4 Step 1** (interpolation) | Stated failure signal is "a literal `${MEET_HOST}`". Compose renders **undefined** variables as the **empty string** with a warning only — the literal can never appear. An operator greps, sees no `${`, and ticks the box while `DJANGO_ALLOWED_HOSTS` is empty. Track B reproduced a real instance: dropping `KEYCLOAK_HOST` yields `https:///realms//protocol/openid-connect/auth`, silently. |
| **D3 Step 4** (image pinning) | `grep -c "latest"` returns **0** against my own override — while `postgres:16` and `redis:7-alpine` float. It also false-negatives on untagged images, which are implicitly `:latest`. The check passes on exactly the configuration it exists to reject. |
| **H1** (CSS served) | Stated failure signal is 404. The frontend nginx has `error_page 404 =200 /index.html`, so a missing file returns **`200 text/html`**, never 404. The check does capture `%{content_type}` and would catch it — but the documented pass criterion trains the operator to read the status code. |
| **C1 Step 4** (bandwidth) | `/sys/class/net/*/speed` returns the *link* speed on virtio, usually `-1`. It cannot produce the hypervisor-provisioned cap that J5 and J6 depend on. |

Track D adds the meta-point: an agentic worker told "a task without an executed check is not done" hits a red check on **task one** (see 1.4), and the cheapest way out is to weaken the check. That sets the tone for the whole run.

### 1.4 HIGH · Phase A's own gates cannot pass ✅ *reproduced*

Task A1 edits `deploy/env.d/common.example` and `RUNBOOK.md`, then asserts `grep -rn "FRONTEND_CSS_URL" .` returns nothing. It returns four surviving hits I never scheduled: **`README.md:33`, `README.md:40`, `docs/PLAN_2026-07-22.md:68`, `docs/PLAN_2026-07-22.md:97`**. The repo's front door keeps the wrong variable name. Same class of defect in Task A2.

Both checks also match the analysis documents that legitimately *discuss* the wrong names, so they can never go green regardless. Scope them with `--exclude-dir=docs` and assert on output, never exit code — reproduced in-session: `--exclude-dir` filtered correctly on one invocation and not another once `--` preceded the pattern, and this machine's `grep` is `ugrep`, which exits `2` where the plan predicts `1`.

### 1.5 MEDIUM · Two risks I overrated, one remediation I got backwards

- **R5 (PKCE + confidential client) — REFUTED.** `mozilla_django_oidc/auth.py:297-307` sends `client_secret` and `code_verifier` in the same POST unconditionally; Clerk advertises `client_secret_post` and `S256`. Keep `OIDC_USE_PKCE=true`. My "unproven pairing" framing was wrong, and Track A supplied the two *real* fallbacks I should have listed instead — see 3.2.
- **R6 (`env_file` interpolation) — REFUTED.** Interpolation works on Compose v2; `format: raw` is the opt-*out*. Both Tracks A and B reproduced it. The real issue is the failure mode (1.3).
- **R1 (X-Forwarded-Proto) — REFUTED as stated, and inverted.** See 2.1. I tested whether the header *arrives*; the actual risk is that a client can *set* it.
- **R12 (TURN) — CONFIRMED, remediation wrong.** See 2.2. My "second flexible IP" recommendation was unnecessarily pessimistic and unnecessarily expensive.
- **R3 (CSRF) — severity overstated.** Low, not Medium. With `X-Forwarded-Proto` arriving, `request.is_secure()` is true and same-origin POSTs pass on the Origin↔Host comparison.
- **R8 (file-based secrets) — acknowledged then dropped.** It appears in no task. Track A supplied the exact mechanism; see 3.4.

---

## 2. Where two or more reviewers agreed independently

Highest-confidence findings: reached separately, by different evidence.

### 2.1 The proxy header risk is inverted — Tracks A + B

Both refuted R1 as written and both landed on the same real defect. nginx forwards inbound headers to upstreams by default (`proxy_pass_request_headers on`; only `Host` and `Connection` are redefined), so `X-Forwarded-Proto` reaches Django fine. **There is no day-one redirect loop.**

The actual problem is that nginx-proxy's `TRUST_DOWNSTREAM_PROXY` defaults to **`true`**, forwarding the *client's* value unchecked:

```
# nginx.tmpl:461-464
map $http_x_forwarded_proto $proxy_x_forwarded_proto {
    default {{ if $globals.config.trust_downstream_proxy }}$http_x_forwarded_proto{{ else }}$scheme{{ end }};
```

Meet's own settings state the precondition being violated (`settings.py:1285-1291`): *"Keep this SECURE_PROXY_SSL_HEADER configuration only if … your proxy strips the X-Forwarded-Proto header from all incoming requests."* Any client can send `X-Forwarded-Proto: https` over plaintext port 80 and Django treats the request as secure — defeating `SECURE_SSL_REDIRECT` and making `request.is_secure()` attacker-influenceable, which drives the CSRF Referer check and the scheme in the OIDC `redirect_uri`.

**Fix:** `TRUST_DOWNSTREAM_PROXY=false` on the nginx-proxy container, plus a spoof test:

```bash
curl -sS -o /dev/null -w "%{http_code} -> %{url_effective}\n" \
  -H "X-Forwarded-Proto: https" http://visio.samourai.app/
# After the fix: 301 to https://. Before: 200 served over plaintext.
```

### 2.2 TURN is available today, free — Track B (correcting my B1.7)

R12 is confirmed: there is no `turn:` block, nothing listens on 443/udp, and §8's "proves TURN over 443 works" is unfalsifiable. My remediation was wrong on the economics.

**B1.7 asserted that 443 belongs to nginx-proxy and cannot be shared. That is true of 443/tcp and irrelevant** — nginx-proxy publishes `"443:443"`, which is **TCP only**. 443/**udp** is free, ufw already has it open, and upstream Meet documents exactly this configuration. I was reserving a paid second IP for something available at zero cost.

Two traps, both verified in LiveKit source, both absent from upstream's documented example:

```yaml
turn:
  enabled: true
  domain: livekit.samourai.app
  udp_port: 443
  tls_port: 0              # REQUIRED — tls_port>0 triggers a cert load (turn.go:134-144) and refuses to start
  relay_range_start: 30000
  relay_range_end: 30100   # REQUIRED — default is 30000-40000 (config.go:589-597)
```

Publish `443:443/udp` and the relay range, and set `{"userland-proxy": false}` in `/etc/docker/daemon.json` or Docker spawns one proxy process per published port.

Honest scope: this covers **UDP/443 only**. It works because firewalls increasingly permit UDP/443 for QUIC. It does nothing for a TCP-443-only firewall with TLS inspection — that needs a second IP or SNI multiplexing, and should be decided after measuring I9, not before.

Also corrected: my claim that `tcp_port: 7881` is "the only fallback restrictive networks get" **overstates its reach**. 7881 is not 443; it helps networks that block UDP but permit arbitrary outbound TCP, a much less restrictive population. A 443-only user today joins the room UI and gets **no media** — the worst failure shape, because it reads as a product bug.

### 2.3 `docker compose config` prints every secret — Tracks B + D

✅ Both confirmed empirically: Compose flattens `env_file` into `environment:`, so the output carries `DJANGO_SECRET_KEY`, `OIDC_RP_CLIENT_SECRET`, `LIVEKIT_API_SECRET`, `DB_PASSWORD` and `DJANGO_EMAIL_HOST_PASSWORD` in cleartext. **My plan runs it three times**, and it explicitly targets agentic workers — for whom the natural debugging move ("let me look at the whole config") dumps five production secrets into a transcript. Over SSH it lands in scrollback and session recordings. The Clerk secret is unrecoverable.

**Fix:** `--no-env-resolution` for structural inspection, `--images` for pins, and a filtered `--format json` selection for the one assertion that needs resolved values. Add to Global Constraints: never run bare `docker compose config`.

### 2.4 Nothing survives a reboot; the upgrade path upgrades nothing — Tracks B + D

Two independent findings, both confirmed against upstream `compose.yaml`:

- **Only `backend` has a restart policy.** `postgresql`, `redis`, `frontend`, `livekit` have none, and my override added none. After a reboot, `backend` returns and its dependencies do not — `depends_on` orders startup within one `up`, it does not restart anything. Compounding: `livekit` depends on redis `service_started` (not healthy) with no restart policy, so losing the boot race is permanent.
- **`RUNBOOK.md:332-338` uses `docker compose restart` after `pull`.** A container's image is bound at creation; `restart` reuses the existing container and the pulled image is never used. Then `migrate` runs **new migrations against old code**. My plan cites §10 five times and never fixes it. The correct command is `up -d`, verified with `docker compose images`.

### 2.5 No backup before migrate, and no rollback anywhere — Tracks B + D

No task takes a `pg_dump` before `manage.py migrate`. First deploy is harmless; every upgrade after is not, and Django migrations are frequently irreversible. There is no documented rollback for a bad migration, a failed TLS issuance, a wrong Clerk config, or a bad image pin. J4 mandates backups and never requires a restore test.

---

## 3. Single-track findings worth acting on

### 3.1 Do not touch production Clerk without a rehearsal — Track D

[README.md:15](../README.md:15) marks Clerk **"live ⚠️ do not touch"**; Memba and Zentai depend on it. My Phase F routes the entire OIDC gauntlet through it and never names the blast radius.

The mechanism nobody had spotted: **`profile` scope is necessary but not sufficient.** Clerk emits `given_name`/`family_name` only if the *instance* collects first/last name — an **instance-level setting shared with Memba and Zentai**. If it is off, the fix for "Visio shows empty names" is a change to their signup forms. And users who signed up before name collection was enabled have null names permanently.

My Task F1 diagnostic offered two causes for an empty name and omitted the likeliest: **the Clerk user record simply has no name stored.**

**Fix:** rehearse the whole flow against Clerk's **development instance** first — separate issuer, JWKS and keys, zero cost — then swap four URLs plus credentials. Snapshot production Clerk settings before any change. Gate on "log in to Memba, log in to Zentai, both succeed" before *and* after.

Track D also argues B1.8 (shared org vs dedicated instance) must be resolved **before** B1.3/B1.5, not deferred: if the answer is "dedicated instance," that changes all four `OIDC_OP_*` endpoints, the credentials and the redirect URI — Phase D and F rework, invalidating every account created in the interim. **Accepted; B1.8 is promoted to the first decision.**

### 3.2 Silent login is on by default and sits on the guest path — Track A

`FRONTEND_IS_SILENT_LOGIN_ENABLED` defaults **true** (`settings.py:390-392`). Every anonymous visitor is sent through `prompt=none` at Clerk via a full-page navigation. The callback special-cases exactly one error (`lasuite/oidc_login/views.py:705-712`):

```python
if error == "login_required" and request.session.get("silent"):
```

Anything else — `interaction_required`, `consent_required`, `invalid_request` — falls through to `login_failure()`. That is a bounce loop or broken landing for **every first-time guest**, on the flagship use case, and my plan never tested it. Kill switch: `FRONTEND_IS_SILENT_LOGIN_ENABLED=false`.

Track A also replaced my single PKCE fallback with the correct ordered set:
1. **`OIDC_USE_NONCE=false`** — `OIDC_USE_NONCE` defaults true and the check is fatal *and outside* the `try/except SuspiciousOperation` (`auth.py:209-213` vs `:319-323`), so a missing `nonce` yields a bare **HTTP 400**, not a graceful failure redirect. Clerk's discovery does not list `nonce` in `claims_supported`.
2. **`OIDC_TOKEN_USE_BASIC_AUTH=true`** — if Clerk ever drops `client_secret_post`.
3. PKCE off — last resort, and per 1.5 probably never needed.

### 3.3 `openssl rand -base64 64` emits two lines ✅ *reproduced*

Verified locally: `-base64 64` → **2 lines**; `-base64 48` → 1. Pasted into an env file, `DJANGO_SECRET_KEY` is truncated at the wrap and the remainder becomes a garbage variable. No error, no warning. `RUNBOOK.md:128` needs `| tr -d '\n'`.

### 3.4 File-based secrets — the exact mechanism (R8 closed) — Track A

`SecretFileValue` checks `<VAR>_FILE` before `<VAR>`, reads the file, and strips exactly one trailing newline:

| Setting | Plain env var | File variant |
|---|---|---|
| `SECRET_KEY` | `DJANGO_SECRET_KEY` | `DJANGO_SECRET_KEY_FILE` |
| `OIDC_RP_CLIENT_SECRET` | `OIDC_RP_CLIENT_SECRET` | `OIDC_RP_CLIENT_SECRET_FILE` |
| `EMAIL_HOST_PASSWORD` | `DJANGO_EMAIL_HOST_PASSWORD` | `DJANGO_EMAIL_HOST_PASSWORD_FILE` |
| DB password | `DB_PASSWORD` | `DB_PASSWORD_FILE` |
| LiveKit key/secret | `LIVEKIT_API_KEY` / `_SECRET` | `…_FILE` |

Caveats: write with `printf '%s'` (a trailing blank line corrupts the secret); a missing path raises at settings import, so the container dies loudly; values carrying `environ_name` resolve eagerly at class-body evaluation, so the file must exist before `meet.settings` imports. This also fixes 2.3 — secrets stop appearing in `docker compose config` — and Track B's L1: today `env_file` fans every secret into the **frontend** (a public static server) and **postgresql** containers, which have no use for them.

### 3.5 Config hardening Track A found that costs nothing

```env
OIDC_STORE_ID_TOKEN=false          # nothing reads it: no SessionRefresh middleware, and the only
                                   # reader returns before reaching it when logout is unset.
                                   # Today it is dead Clerk PII in every Redis session.
OIDC_USERINFO_ESSENTIAL_CLAIMS=email   # default [] requires only `sub`; without this a Clerk
                                   # identity with no email yields a silent null-email account
LIVEKIT_FORCE_WSS_PROTOCOL=true    # matches upstream's own production Helm values; my plan had
                                   # it as an if-it-breaks fallback (Track B, R4 resolved)
```

**Never set `OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION=true`** — given the shared-org model it creates an account-takeover path via an unverified Clerk email matching an existing Meet user; `email_verified` is checked nowhere in the chain.

Two accepted-and-documented, not fixable: logout is a CSRF-able GET (`ALLOW_LOGOUT_GET_METHOD` defaults true and the frontend's own button uses GET — disabling it breaks the product), and `/jwks` is mounted publicly at the site root returning a 500 when unconfigured, which will pollute Sentry.

### 3.6 Asset mounting — one refutation, one footgun — Track C

**BLOCKER-3 stands as a defect but my reasoning was over-cautious.** The frontend image's nginx has `root /usr/share/nginx/html; location / { try_files … }`, so `./custom:/usr/share/nginx/html/custom:ro` **is** served correctly. I inferred from `theming.md`'s `/assets` wording that a non-`assets` path would not work; it does.

**The footgun is the documented path.** Bind-mounting a *directory* over `/usr/share/nginx/html/assets` replaces Vite's entire build output — `index-*.js`, `index-*.css`, the MediaPipe wasm — and the app will not boot. Upstream's own reference build copies **individual files**. Every logo/icon override must be a per-file mount.

Track C also enumerated what my plan missed entirely: favicons and PWA icons live at the web **root**, not under `/assets`; `site.webmanifest` ships with empty `name`/`short_name`; `FRONTEND_MANIFEST_LINK` is *not* the PWA manifest (it renders an external "en savoir plus" link); there are no `og:`/`twitter:` meta tags to override at all; and `VITE_APP_TITLE` is **not** settable via `--build-arg` on the shipped Dockerfile — `theming.md` is simply wrong, the value comes from `.env.production`. My "accept the upstream title for v1" recommendation stands, but the consequence is larger than a browser tab: "LaSuite Meet" appears in on-screen copy in six places.

### 3.7 Legal, licensing and moderation — Track D

- **No `LICENSE`, no `NOTICE`** ✅ verified. An unlicensed public repo is "all rights reserved," and this one redistributes MIT-derived upstream files (`deploy/env.d/common.example`, `deploy/hosts.example`). MIT requires the notice *in copies*; a UI footer satisfies neither clause. The obligation attaches to **this repository**.
- **Missing and legally mandatory in France:** *mentions légales* (LCEN art. 6-III — coop identity, SIREN, publication director, **and the host's** name and address) and a *politique de confidentialité* (GDPR Art. 13). A CGU is neither.
- **J1 needs a table, not a line:** Postgres user records, room metadata, Clerk ID tokens in Redis, **nginx-proxy access logs (IP addresses are personal data, default retention forever)**, Sentry events, Resend logs. And the strongest privacy point is buried as an out-of-scope note — **no recording, no transcription, media is never persisted.** Lead with it.
- **The abuse contact has no lever behind it.** With `ALLOW_UNREGISTERED_ROOMS=True` and no recording, a report cannot be acted on: no content visibility, no attribution for ad-hoc rooms, no ban. Minimum before promotion: a documented kill-room command, a slug blocklist, rate-limiting on room creation. If the answer is "ad-hoc rooms are unattributable and we accept that," **write that down** rather than implying a capability that does not exist.
- **DSA almost certainly does not bite** — ephemeral real-time conferencing does not "store and disseminate to the public." Do not over-engineer.
- **No cookie banner needed** — the Django session cookie is strictly necessary. Revisit only if analytics are added.

### 3.8 `ALLOW_UNREGISTERED_ROOMS=True` deletes the Stage 5 business boundary — Track D

[docs/PLAN_2026-07-22.md:44](PLAN_2026-07-22.md:44) states *"only room creation needs an identity. That boundary is … exactly where 'Samouraï Member' will sit in Stage 5 — no re-architecture needed later."*

With the flag `True`, **anyone can create a working room from a URL with no account.** That boundary does not exist. What an account actually buys is a *persistent, owned, administrable* room — still a viable paid boundary, but not the one Stage 5 is designed around. It is also the same fact that makes ad-hoc rooms unattributable for moderation. [README.md:39](../README.md:39) describes the same non-existent gate.

### 3.9 Capacity target is ~3× optimistic — Track B

LiveKit's published benchmark: a **16-vCPU** instance reaches 85% CPU at 150 publishers + 150 subscribers. Scaled to 4–8 vCPU that is roughly **40–75 concurrent participants**. J7's 200-participant benchmark is not a measurement the target hardware can pass — it is a spec change. Also: Scaleway includes egress in the instance price for EU instances, so the 60–150 €/mo estimate is dominated by instance cost, not traffic; the risk is a hard bandwidth *cap*, not a bill. Honest framing: measure at 10/50, extrapolate, do not promise 200.

### 3.10 Smaller items adopted

**Track B:** Redis 7 is wire-compatible and needs no migration (upstream ships no volume — clean start); pin `redis:7.4-alpine`, not floating `7-alpine`; LiveKit shares the Redis on **db 0** while Django uses **db 1**, so no collision, but AOF now persists LiveKit routing state (self-healing via TTL, but a behaviour change); `MEDIA_ROOT=/data/media` has **no volume** — harmless for v1's feature set, silent data loss the moment any upload feature is enabled; Let's Encrypt `certs`/`acme` volumes live in a *different* compose project and belong in J4's backup scope; **ufw is decorative for published ports** — Docker's `DOCKER-USER` chain bypasses it, so exposure is governed by `ports:` in compose, and the real risk is a future debug `"5432:5432"`; no log rotation anywhere on an unbounded json-file driver, on the same volume as the database.

**Track D:** `livekit-server.yaml` ships a `<your livekit secret key>` placeholder that **no check in my plan scans**, and nothing asserts it matches `LIVEKIT_API_SECRET` — mismatch means healthy stack, TLS fine, and **every LiveKit token fails signature validation**; `.gitignore` ✅ verified porous — the Postgres data directory, Redis AOF, `pg_dump` output, `deploy/.env.prod` and `deploy/custom/` are all trackable today (`deploy/env.d/` itself is airtight); `git check-ignore` cannot detect an **already-tracked** file, so B1's check cannot fail loudly; `createsuperuser` is interactive and will hang an agentic worker — and it is the **break-glass path if Clerk is misconfigured**, which my plan never says; `User.id` is a **UUID**, so Task F1's `order_by('-id')` inspects a *random* user and only appears to work on a fresh database with one user; `nc -zu` on UDP reports success against a DROPping firewall and my plan never said to run it from **outside**; the **Scaleway security group** is a second independent filter that `ufw status` cannot see; no CI, no secret scanning, no branch protection, and no rotation procedure for any of the five secrets.

---

## 4. What the reviews confirmed

Stated briefly, because it is the smaller half.

- **The drift report is trustworthy.** Track D spot-checked 11 line citations against live `settings.py`: all 11 land on the declaration claimed, and the stated file length (1369) is exact. Track C confirmed `panda.config.ts`, `theming.md` and `settings.py` are **byte-identical between `main` and `v1.24.0`**, so the offline analysis is valid for the pinned image. Track B MD5-matched `compose.yaml` and `livekit-server.yaml` against upstream today.
- **All three blockers are real.** BLOCKER-1 confirmed end-to-end through the delivery chain (`settings.py:375-380` → `/api/v1.0/config/` → `AppInitialization.tsx:16-24` appends the `<link>`); `FRONTEND_CSS_URL` exists nowhere in the codebase. BLOCKER-2 confirmed by local Panda codegen. BLOCKER-3 confirmed as a defect (see 3.6 for the reasoning correction).
- **All four traps confirmed.** Trap 3 verified verbatim at the cited lines, including that `OIDCLogoutCallbackView` and `OIDCBackChannelLogoutView` are harmless when unconfigured.
- **Trap 4 is the strongest work in the package.** Both the observation that the original guest-join test never touches the flag and the I4/I5 split were independently confirmed.
- **The callback URI is exactly right** — `https://visio.samourai.app/api/v1.0/callback/`, trailing slash included, and **nothing else needs registering** at Clerk. `authenticate/` is a local entry point; `logout-callback/` is used only when a logout endpoint is set; `backchannel-logout/` is unsupported by Clerk.
- **The `compose.override.yaml` strategy is sound**, and Track B verified the merge semantics empirically: `image` and `command` replace, `environment`/`networks`/`volumes` merge, and the upstream `default.conf.template` mount **survives**. Editing `compose.yaml` in place as RUNBOOK §5 instructs would indeed be erased by §10. *(One internal contradiction: my Task E3 Step 3 instructed editing `default.conf.template` in place — the exact failure mode the design exists to prevent. Moot given 2.1, but corrected.)*
- **Declining the `VITE_APP_TITLE` rebuild is right**, and so is refusing to promise TURN we do not have.

---

## 5. Revised decisions

| ID | Was | Now |
|---|---|---|
| **B1.8** | deferred go/no-go on shared Clerk org | **Promoted to first decision, blocking B1.3/B1.5.** Shared org or dedicated instance determines endpoints, credentials and redirect URI; unrevisitable after Phase D without invalidating every account created meanwhile. |
| **B1.7** | ship without TURN; revisit with a paid second IP | **Enable LiveKit TURN on UDP/443 now** — free, 443/udp is unbound, ufw already open. Measure I9, then decide whether the TCP-443-only tail justifies a second IP or SNI multiplexing. |
| **B0** *(new)* | — | **Rehearse Phase F against Clerk's dev instance** before touching production. Snapshot settings; gate on Memba + Zentai login before and after. |
| **B1.10** *(new)* | — | Confirm `ALLOW_UNREGISTERED_ROOMS=True` is the intended product boundary, and correct `docs/PLAN_2026-07-22.md:44` and `README.md:39`. |
| **B1.11** *(new)* | — | Adopt file-based secrets now (mechanism in 3.4) or decline in writing. Recommendation: **adopt** — it also closes 2.3. |
| **B1.12** *(new)* | — | Owner-supplied brand assets: logo, favicons, PWA icons, `site.webmanifest` values. |
| **B1.13** *(new)* | — | Accept or mitigate: logout does not clear the Clerk SSO session. RUNBOOK §4 trap 3 names a mitigation my plan dropped. |
| **J2** | "caps — max participants, max duration" | **Meet exposes neither setting.** Enforcement must be LiveKit-side (`max_participants` on `CreateRoom`, `empty_timeout`/`departure_timeout`). Decide whether v1 ships uncapped and say so in the CGU. |
| **J5** | "Sentry already runs" | `SENTRY_DSN` is set nowhere and no task adds it. Note the trap while adding it: `settings.py:69` documents `DJANGO_SENTRY_DSN` but `:448` declares `environ_name="SENTRY_DSN"` — **BLOCKER-1's exact failure mode, inside a Phase J checkbox.** |
| **J7** | benchmark at 10/50/200 | Measure at 10/50 and extrapolate. 200 is ~3× what 4–8 vCPU can serve (3.9). |

---

## 6. Priority order

**Before any host work — repo-only, no credentials required:**
1. Fix the `ListValue` syntax everywhere (1.1). Everything downstream is worthless without it.
2. Replace the theme with Track C's ramp; fix the attribution hook (1.2).
3. Make Phase A's gates passable; add `README.md` and `docs/PLAN_2026-07-22.md` (1.4).
4. Close `.gitignore`; add `LICENSE` + `NOTICE`; add CI with secret scanning (3.7, 3.10).
5. Fix the four hollow checks (1.3); ban bare `docker compose config` (2.3).
6. Fix §10's upgrade path; add restart policies, `pg_dump`-before-migrate, and rollback blocks (2.4, 2.5).

**Before touching production Clerk:**
7. Resolve B1.8. Then rehearse against the dev instance (3.1).

**Before promotion:**
8. TURN on UDP/443 (2.2); `TRUST_DOWNSTREAM_PROXY=false` (2.1); test silent login (3.2); mentions légales + privacy policy + a real moderation lever (3.7).

---

## 7. Status

**This plan is not ready to execute, and none of it has been.** The four reviews found one defect that would have broken authentication outright, one that would have shipped an inaccessible interface, and four checks that would have reported success while the system was broken.

They also found that the underlying analysis was sound. The traps were real, the blockers were real, and the drift diff was accurate. What failed was the layer between diagnosis and execution — writing fixes without testing that the fixes parse, and writing checks without testing that the checks can fail.

Awaiting owner review. Merge conditions are **not** met: there is no CI in this repository, so "CI all green and verified" cannot be satisfied, and the proposal is explicitly reserved for owner review.
