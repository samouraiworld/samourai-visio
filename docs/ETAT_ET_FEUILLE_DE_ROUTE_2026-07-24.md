# State of play and roadmap — 2026-07-24

> Written to close one working session and open the next with a clean context.
> Everything below was verified against the live instance or the repo, not
> inferred. Where something is unproven, it says so.

**Status: `visio.samourai.app` is live and usable. It is NOT promoted, and it
must not be announced until the Phase 1 items below are closed.**

---

## 1. What exists today

| Layer | State |
|---|---|
| **Host** | Scaleway instance, Paris (verified: AS12876, `62.210.92.69`). Docker, ufw, node_exporter. Operated by LOurs. |
| **Stack** | La Suite Meet `v1.24.0`, LiveKit `v1.13.4`, Postgres 16, Redis 7.4 — all pinned in `deploy/compose.override.yaml`. |
| **Auth** | Clerk (`clerk.samourai.app`), OAuth app "Visio Samouraï" registered. Guest join needs no account. |
| **Mail** | Scaleway Transactional Email. **Verified end to end** — an invitation was delivered. |
| **TLS / DNS** | Both hosts resolve to the instance; DNS managed on Netlify DNS. |
| **Theme** | Samouraï CSS live and applied (`/custom/style.css` → `200 text/css`, `custom_css_url` advertised). |
| **Landing + legal** | Merged in [#11](https://github.com/samouraiworld/samourai-visio/pull/11). **Not yet deployed to the host** — see Phase 0. |
| **CI** | 8 gates, green on `main`. |

### What the product actually does

- Anonymous visitor → lands on our page → one click opens a working room.
- Signed-in user → keeps Meet's own home (create instant/scheduled room).
- Inside a room → the untouched DINUM interface.

There is **no fork**. Every delta lives in configuration, a runtime CSS theme,
and a static landing directory. That is what makes upstream upgrades cheap, and
it is the single most important constraint on this repo.

---

## 2. Decisions already settled — do not re-open without a reason

| Decision | Why |
|---|---|
| **No fork of the application** | Upstream improvements reach users for free; no image, no build pipeline, no upgrade debt. |
| **Landing via `FRONTEND_EXTERNAL_HOME_URL`** | Upstream-supported hook. Redirects *anonymous* visitors only, so signed-in users keep Meet's home and rooms are untouched. |
| **Landing served same-origin** from the `./landing` mount | The address bar never leaves `visio.samourai.app`. |
| **Our own legal pages; never link upstream's** | `/mentions-legales` and `/conditions-utilisation` serve DINUM's notices — French State SIREN, a serving public official as publication director, service "reserved for State administrations". Hardcoded in React; no env var overrides them. Gated by `check-hygiene.sh`. |
| **Zero third-party resources** | Gated twice: `check-hygiene.sh` on the repo, `preflight.sh public` on the *deployed* theme. |
| **`FRONTEND_IS_SILENT_LOGIN_ENABLED=false`** | Upstream default sends every anonymous visitor to Clerk before they click. A guest's browser now never contacts Clerk — which is what lets the privacy policy say so. |
| **Membership shown as "Bientôt disponible"** | Price announced, no dead link, because no checkout exists. |
| **Guest-first, but stop *selling* "no account"** | We intend to sell a 5,99 €/month membership; the copy must not teach visitors they never need an account. |
| **Clerk (US) is a known, disclosed gap** | Declared openly in the privacy policy. Replacement is a project, not a task. |

---

## 3. Roadmap

### Phase 0 — deploy what is merged (blocks everything else)

Nothing in #11 is live yet. On the host, in `~/visio`:

1. Copy the repo's `landing/` directory to `~/visio/landing/` (it carries
   `logo-mark.png`, `legal.css`, `mentions-legales/`, `confidentialite/`).
2. Copy `theme/custom.css` → `~/visio/custom/style.css` **again** — it changed
   (the third-party font import was removed).
3. Put a real `custom/logo.png` in place (source:
   `samourai-hub/public/logo-mark.png`). Without it every invitation e-mail
   ships a broken image.
4. Add to `env.d/common`: `FRONTEND_EXTERNAL_HOME_URL`, `DJANGO_LANGUAGE_CODE`,
   `FRONTEND_IS_SILENT_LOGIN_ENABLED=false` — see `deploy/env.d/common.example`.
5. Add the `./landing` volume to `~/visio/compose.override.yaml`.
6. `docker compose up -d` — **not `restart`**, which does not reload env.
7. `scripts/preflight.sh config` then `scripts/preflight.sh public`.
8. Walk RUNBOOK §8 by hand.

### Phase 1 — required before any public promotion

| # | Item | Note |
|---|---|---|
| 1.1 | **Enforce the retention the privacy policy already promises** | The published page states access logs 7 days, accountless rooms purged monthly, accounts deleted after 12 months idle. **None is implemented.** nginx-proxy's json-file logs are unbounded. A published retention period nothing enforces is a written commitment to a control that does not exist. Implement, or amend the page. |
| 1.2 | **Missing legal fields** | LCEN wants a telephone number for the publisher; add a VAT number if Samouraï Coop is VAT-registered. Both absent from `mentions-legales/`. |
| 1.3 | **Our own CGU** | Upstream's remain reachable by direct URL and describe a service for State administrations. Nothing links to them, but they exist on our host. |
| 1.4 | **Caps** | Meet exposes none; enforce LiveKit-side (`max_participants`, `empty_timeout`, `departure_timeout`). |
| 1.5 | **Backups** | `pg_dump` on cron, off-box, **restore-tested once**. An untested backup is not a backup. |
| 1.6 | **Monitoring** | Uptime + bandwidth alert. Note the trap: `settings.py:69` documents `DJANGO_SENTRY_DSN` but `:448` declares `environ_name="SENTRY_DSN"` — the documented name does nothing. |
| 1.7 | **Load measurement** | At 10 and 50 concurrent participants, then extrapolate. LiveKit's own benchmark puts 4–8 vCPU at roughly 40–75 participants; do not promise 200. |

> **Progress — 2026-07-24, after this document was written.**
> **1.1 is closed in the repo**: log retention is implemented (journald,
> `deploy/host/`, RUNBOOK §8bis, preflight checks with self-test mutations),
> and the two promises that machinery could not honestly back were reworded to
> verified reality — rooms created without an account are **never stored**
> (`core/api/viewsets.py:257-277` builds the response in memory; now asserted
> by `check-upstream-contract.sh`), and account deletion is **on request**,
> deliberately, because Clerk accounts are shared with Memba/Zentai and an
> idle-on-Visio timer would delete accounts active elsewhere. The host-side
> install (RUNBOOK §8bis) joins the Phase 0 window; `preflight.sh` fails until
> it has run.
> **1.2 is half closed**: VAT `FR 54 830 485 108` added to the mentions
> légales; the publisher telephone number is still missing.
> **1.3 is closed in the repo** (second PR): our own CGU at
> `landing/conditions-utilisation/`, linked from every footer — and the gap
> the item actually described is closed too: a gateway override
> (`deploy/nginx/default.conf.template`, upstream's template plus marked
> blocks) 301s all **three** hardcoded DINUM routes to our pages —
> `/mentions-legales`, `/conditions-utilisation` **and `/accessibilite`**,
> which this document had not listed. Gates: preflight asserts the redirects
> (config: file + merged mount source; public: live 301s), and
> `check-upstream-contract.sh` diffs the template against upstream with our
> blocks stripped, so gateway drift blocks the next version bump instead of
> shipping. Host needs `deploy/nginx/` copied to `~/visio/nginx/` in the
> Phase 0 window (RUNBOOK §3 note + §9).
> **1.4 is closed in the repo** (third PR): `room:` block in
> `livekit-server.yaml.example` — `auto_create: true` pinned (the guest flow
> depends on it), `max_participants: 30` (conservative until 1.7 measures),
> `empty_timeout: 300` (the setting that makes the privacy page's
> vanishing-room sentence true), `departure_timeout: 20`. Meet never calls
> CreateRoom (verified v1.24.0), so these server defaults bind every room.
> Room **duration** stays uncapped — no such knob exists at v1.13.4; noted in
> RUNBOOK §9. Preflight asserts the caps (self-test mutations included);
> the contract gate pins the key names against the livekit tag read from the
> compose pin. Host: add the block to `~/visio/livekit-server.yaml` +
> recreate livekit.

### Phase 2 — engineering debt from the 2026-07-24 review

Ranked. All verified, none blocking.

1. `RECORDING_ENABLE=False` is only an upstream default; the landing claims
   "jamais d'enregistrement". Set it explicitly, gate it, and assert it in
   `check-upstream-contract.sh`.
2. `check-upstream-contract.sh` does not assert `FRONTEND_EXTERNAL_HOME_URL`
   still exists upstream. On a rename, no gate goes red — the public phase
   merely downgrades to SKIP.
3. `preflight.sh public` keys the landing check on `id="start-btn"`, a dead
   attribute nothing else references — a prime deletion target. Couple it to
   something load-bearing.
4. Documented failure symptom for a missing landing mount is wrong: a mounted
   directory with no `index.html` returns a bare nginx **403**, not the SPA
   fallback. Affects RUNBOOK, `common.example`, `preflight.sh`, the self-test.
5. Gate `landing/logo-mark.png` the way `custom/logo.png` already is, and strip
   its XMP/EXIF (`oxipng --strip safe`).
6. Accessibility: no `<main>` landmark; the skip link targets a `div`; add
   `scroll-margin-top` for the 63px sticky nav; `.compare` clips below ~332px.
7. RUNBOOK cites `Home.tsx:165-175`; at v1.24.0 the relevant lines are 149 and
   156-160. Line citations are load-bearing in this repo.
8. `NOTICE.md` says `Copyright (c) 2024 DINUM`; upstream v1.24.0 reads
   `2024-2025 DINUM/Etalab`. The repo is public now.
9. `.gitignore` does not cover `.claude/settings.local.json` or
   `.playwright-mcp/` (no exposure found — a fresh clone is clean — but close it).

### Phase 3 — product

- **Greffon packaging** — draft at `deploy/greffon/`. Blocked on Greffon
  supporting a stable custom domain (Clerk's redirect URI is fixed).
- **Membership checkout** — the 5,99 €/month flow. The landing and the hub both
  carry the same "coming" stub. E-mail capture was floated and deferred; it
  probably belongs on the hub once, not per app.
- **Clerk → European IdP** — the only non-EU dependency left.

---

## 4. Traps this stack sets

Read before changing anything. Each one has cost time already.

1. **List env values are comma-separated, never JSON.** `["a","b"]` parses as
   `['["a"', '"b"]']` and silently empties every display name. Upstream's own
   template gets this wrong.
2. **A missing bind-mount returns `200 text/html`**, not 404 — the frontend
   nginx ends with `error_page 404 =200 /index.html`. Assert on content-type or
   content, never on status.
3. **`DJANGO_LANGUAGE_CODE` does not set the interface language.** The SPA
   resolves it client-side via i18next browser detection; `LANGUAGE_CODE`
   appears in none of its JS chunks. It sets the backend default and the mail
   fallback only.
4. **`docker compose restart` does not reload env or images.** Always `up -d`.
5. **`docker compose config` prints every secret.** Use `--no-env-resolution`
   or `--images`.
6. **The Scaleway security group is a second firewall** that `ufw status`
   cannot see. A green ufw with a closed security group is the classic "signal
   works, no media".
7. **`openssl rand -base64 64` wraps onto two lines** and silently truncates
   `DJANGO_SECRET_KEY`. Use `| tr -d '\n'`.
8. **The LiveKit secret lives in two files** and a mismatch is invisible: the
   stack is healthy, TLS is fine, and every token fails signature validation.

---

## 5. Conventions

- **English everywhere in the repo** — comments, docs, commits, PRs, issues.
  Only user-facing product copy is French (the landing and the legal pages).
- Never commit to `main`; feature branch + PR.
- No AI attribution in commits, PRs, tags or release notes.
- Every check must be able to fail: add a mutation to
  `scripts/preflight-selftest.sh` for each new one. A check that cannot fail
  reads as coverage while proving nothing — this repo has shipped that mistake
  twice and both times it was caught late.
- Assert on command output, never on grep exit codes.
