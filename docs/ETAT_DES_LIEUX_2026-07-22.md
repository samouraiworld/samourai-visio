# Reportz.dev — État des lieux réel

> Audit conducted 2026-07-22. Evidence-based: every claim below is traceable to a file, a line number, a git object, or a live HTTP response.
> Scope: `reportz.dev/reportz`, `reportz.dev/gnolove-source`, `Gno/Memba`, and the upstream `samouraiworld/gnolove`.

---

## TL;DR

| Project | Real state | Verdict |
|---|---|---|
| **Reportz.dev** | ~2,150 lines of fork-original code, written in a single ~40-minute session on 2026-01-11 and abandoned mid-refactor. **Frontend does not build.** Database contains **zero** GitHub records. Every metric on the landing page is a hardcoded literal. | **~25–30% of a multi-ecosystem product.** An architectural sketch, not a product. |
| **Memba** | 1,173 commits, ~240k LOC, ~5,100 test cases, real CI gates, live in production. | **Genuinely production-grade.** Single-maintainer (bus factor 1). |
| **The "Gnolove + Memba" fork thesis** | Never executed. Reportz took Gnolove's *pipeline*; Memba built the *analytics UI*. The two halves have never been joined. | **The actual product is still unbuilt.** |

---

## 1. Reportz.dev — the fork

### 1.1 History

Four commits, all on **2026-01-11**, spanning **17:07 → 17:46** — a single 39-minute session.

| Commit | Time | Scope |
|---|---|---|
| `84a2088` Initial commit | 17:07 | Squashed snapshot of upstream HEAD + 3 new config files + rebranded README/package.json |
| `43ef471` backend ecosystem layer | 17:18 | +778/−1 — config loader, service, handler, models |
| `3c14d33` rebrand frontend | 17:42 | +71/−87 — strings only |
| `56c7e8b` ecosystem selector | 17:46 | +276/−51 — selector, context, header |

Plus **20 modified files (+245/−134) and 7 untracked paths** never committed since.

Net fork-original code, committed + uncommitted: **~2,150 lines**, of which 582 are markdown.

### 1.2 It does not build

`npx next build` fails at **three successive stages**:

1. **ESLint — 320 errors.** 302 are fork-introduced; 295 are `indent` violations (new files written with 4-space indent against a 2-space rule). Nearly all auto-fixable.
2. **TypeScript — 2 errors.** `src/app/layout.tsx:29` passes `string | undefined` to `new URL()`; `ecosystem-cards.tsx:39` reads a `description` property that doesn't exist on `EcosystemMetadata`.
3. **Prerender — 13 routes fail.** `EcosystemProvider` calls `useSearchParams()` and is mounted in the root layout with **no `<Suspense>` boundary**, poisoning static generation of every route. Fork-introduced regression; upstream has no such provider.

The Go backend, by contrast, is clean: `go build ./...` and `go vet ./...` both exit 0.

`pnpm dev` still works. That is currently the only viable demo path.

### 1.3 There is no data

`server/reportz.db` (260 KB, the live DB):

```
ecosystems               2      users            0      pull_requests   0
ecosystem_organizations  5      commits          0      issues          0
ecosystem_repositories  18      reviews          0      milestones      0
ecosystem_stats          2      repositories     1      sync_statuses   1
```

A sync pass **did** complete (`sync_statuses.last_synced_at = 2026-01-11 18:01:26 UTC`) and ingested **zero GitHub rows**. Errors are logged but never fatal, so it failed silently.

Every number visible on the landing page comes from `server/cmd/seed/main.go:66-95`:

```go
gnoland: 154 devs / 12,450 contributions / velocity 45.2
mistral: 289 devs /  8,900 contributions / velocity 67.5
```

These are literals. There is **no code anywhere in the repo** that computes `EcosystemStats` from real activity.

### 1.4 The ecosystem abstraction — how deep it actually goes

**The good part is real.** Four GORM tables (`ecosystems`, `ecosystem_organizations`, `ecosystem_repositories`, `ecosystem_stats`), auto-migrated, populated from `server/config/ecosystem-config.yaml` by a loader with genuine validation (required fields, unique IDs, charset checks, `${ENV_VAR}` expansion) and an upsert service that runs on every boot. This is not a hardcoded enum. Verified live in the DB: 2 ecosystems, 5 orgs, 18 repos.

**The load-bearing part was never built.**

> `server/main.go:73` still calls `models.GetRepositoriesFromConfig()` → reads the **`GITHUB_REPOSITORIES` environment variable** → feeds `sync.NewSyncer()`.
>
> **Nothing in `server/sync/` ever reads `EcosystemRepository`.**

So you can add an ecosystem to the YAML and it will appear in the dropdown and on the landing cards — and no data will ever be ingested for it. `ecosystem_repositories` holds 18 rows; the `repositories` table holds **1** (`gnolang/gno`, from the env var).

**Endpoint coverage: 4 of 28.** Only `/stats`, `/last-prs`, `/issues`, `/contributors/newest` honour `?ecosystem_id=`. `/repositories` accepts the parameter and discards it. `/milestones/{number}` hardcodes `repository_id = 'gnolang/gno'`.

### 1.5 Four defects that make the demo lie

**A. JSON key-case mismatch kills every logo and every feature flag.**
`server/config/loader.go:29-42` carries only `yaml:` tags, no `json:` tags. Marshalling produces Go field names:

```json
{"Blockchain":true,"GovDAO":true}   {"LogoURL":"/images/ecosystems/gnoland.svg"}
```

Everything downstream expects snake_case. `handler/ecosystem.go:131` does `json_extract(e.metadata, '$.logo_url')` → always NULL. `header.tsx:18` checks `features?.blockchain` → always `undefined` → the "feature flags automatically toggle blockchain UI" claim in `RELEASE_NOTES.md:19` does not work at all.

**B. Duplicated columns zero out the headline metric.**
An uncommitted rename added `gorm:"column:merged_prs_7d"` after the table existed. AutoMigrate added the new columns without dropping the old:

```sql
merged_p_rs7d, velocity7d, velocity30d      -- populated: 15.5 / 45.2
merged_prs_7d, velocity_7d, velocity_30d    -- ALL NULL   ← what the handler reads
```

Velocity renders as `0.0` for every ecosystem.

**C. "Global" mode — the new default — breaks three pages.**
`ecosystem-context.tsx:44` now defaults to `null`. Five hooks gained `enabled: !!currentEcosystem?.id`. `/` is guarded, but `/analytics`, `/teams` and `/report` render anyway and sit on **permanent spinners** in the default state.

**D. Missing assets.** `ecosystem-config.yaml` points logos at `/images/ecosystems/*.svg`. `public/images/` contains only `header.png`. No `ecosystems/` directory exists. The OG image is absent too.

### 1.6 Hygiene

- **Tests: zero.** No `*_test.go`, no `*.test.ts(x)`, no test runner in `package.json`.
- **Frontend CI: none.** This is precisely why 320 lint errors and 2 type errors landed unnoticed.
- **Backend CI: inherited and dead.** `graphgl-gen.yml` triggers on `main`; the fork's branch is `master`, so it never fires. `deploy_backend_org.yml` would push `ghcr.io/<owner>/gnolove-server` and `cd Gnolove` on the target host.
- **No `origin` remote.** `git remote -v` returns nothing. There is no `git merge upstream/main` path — future Gnolove updates must be merged by hand.
- **`server/reportz.db` is untracked but not gitignored** (`.gitignore` only covers `database.db`) — a commit-a-binary-DB hazard.
- **`package-lock.json` (524 KB) sits alongside `pnpm-lock.yaml`** while `package.json` declares `packageManager: pnpm@8.15.1`.

### 1.7 Documentation that isn't true

| Claim | Location | Reality |
|---|---|---|
| "Backend: Go, PostgreSQL, Redis"; requires PostgreSQL 14+ / Redis 7+ | `README.md:30,44-45` | SQLite (`server/db/db.go:20`) + in-process ristretto cache |
| `go run . --validate-config`, `--sync-ecosystem <id>` | `docs/add-ecosystem-guide.md:122,139` | No flag parsing exists in `main.go` |
| `/ecosystems/<id>` page | `docs/add-ecosystem-guide.md:172` | No such route |
| Needs clean install for `@radix-ui/react-select` | `RELEASE_NOTES.md:35` | Never added; code uses Radix Themes' bundled Select |
| `server/config/ecosystem-schema.json` (128 lines) | — | Dead artifact; nothing loads or validates against it |

### 1.8 Residual Gno hardcoding

Beyond the intended `ecosystem-config.yaml`, **18 further locations** still hardcode Gno/Samouraï identifiers. The most consequential:

- `server/handler/stats.go:287` — fallback `[]string{"gnolang/gno"}` → unknown ecosystem silently serves Gno data
- `server/handler/milestone.go:20` — milestones are Gno-only, permanently
- `server/handler/ai/prompts.go:70-95` — the AI report prompt is a hardcoded glossary of 8 Gno/Samouraï repos
- `src/constants/teams.ts` (115 lines) — the entire `/teams` page is a hardcoded roster of Gno core-team GitHub logins
- `src/constants/menu-items.ts` — nav submenu is still literally labelled **"Gnoland"**
- `server/handler/leaderboard.go:132,139` — webhook messages still link to `gnolove.world`

### 1.9 Completion by area

| Area | State | % |
|---|---|---:|
| Ecosystem config → DB pipeline | Working, verified | 85% |
| Ecosystem read API (5 endpoints) | Working; NULL logos, 0 velocity | 70% |
| Ecosystem-scoped filtering | 4 of 28 endpoints | 15% |
| **Multi-ecosystem GitHub ingestion** | **Not started** | **0%** |
| **EcosystemStats computation** | **Not started** | **0%** |
| Landing / global leaderboard UI | Written; wrong data; won't compile | 55% |
| Rebranding | UI ~80%, backend/CI/nav ~20% | 55% |
| Build & correctness | Fails at 3 stages | 0% |
| Tests / CI | Nonexistent | 0% |

**Overall: ~25–30%.**

### 1.10 Shortest path to a demo

**Tier 1 — make it build and stop lying visually (~1–2 hours, all mechanical):**

1. Add `json:` tags to `server/config/loader.go:29-42`, `DELETE FROM ecosystems`, restart → fixes logos, avatars, feature flags. *15 min, highest value-per-minute in the repo.*
2. Fix `layout.tsx:29` and add `description?: string` to `EcosystemMetadata` → clears both TS errors. *5 min.*
3. Wrap `<EcosystemProvider>` in `<Suspense>` → clears all 13 prerender failures. *10 min.*
4. `pnpm format` + `eslint --fix` on the 10 new files → clears ~300 of 320 errors. *5 min.*
5. `DROP TABLE ecosystem_stats;` and re-seed → leaderboard stops showing 0.0. *10 min.*
6. Guard global mode on `/analytics`, `/teams`, `/report`. *20 min.*

Result: a screenshot-quality demo where **every metric is still fake** and clicking into any ecosystem shows an empty dashboard.

**Tier 2 — one ecosystem with real data (~half a day + sync time):** fix the silent GitHub sync failure (check token scopes first), then replace `main.go:73` with a query over `ecosystem_repositories` (~20–40 lines).

**Tier 3 — make the thesis true (~1–2 days):** write `ComputeEcosystemStats` — aggregate PRs/issues/commits joined through `ecosystem_repositories`, 7d/30d windows, velocity, trend. ~200–400 lines. **Until this exists, "Open Source Ecosystem Intelligence" is a UI mock.**

---

## 2. Memba — for comparison

The contrast matters, because it shows the gap is discipline and time, not capability.

| Metric | Value |
|---|---|
| Commits | **1,173** (2026-02-24 → today) |
| Code | ~240k LOC + 54k lines of docs (222 files) |
| Contributors | **~1,103 commits from one human**, 69 Dependabot, 1 other |
| Backend tests | 602 `func Test*`, **42.6% coverage**, all 16 packages pass |
| Frontend tests | 428 unit files / **4,184 cases**, + 338 Playwright e2e |
| CI | 9 workflows with real gates: coverage floor, bundle-size budget, feature-flag safety, light-theme colour gate, proto breaking-change detection, Lighthouse |
| Production | `memba.samourai.app` → 200 · `memba-backend.fly.dev/health` → 200 |
| TODO/FIXME density | **9 across the entire codebase.** Zero `panic("unimplemented")`. |

Caveats worth naming: `contracts/` is an **empty shell** with a stale README (real realm source lives in the private `samcrew-deployer`); the MCP servers are thinly tested; and the docs undercount the tests (README says 243 Vitest files, actual is 428).

**Structural risk: bus factor 1**, plus dependence on external services it doesn't control — `backend.gnolove.world` and `monitoring.gnolove.world`.

---

## 3. The "fork of Gnolove AND Memba" thesis — what actually happened

This is the most important finding in the audit.

**Gnolove** (`samouraiworld/gnolove`, 6 ⭐, 2 open issues, last touched 2026-06-05) contains **both** a Next.js frontend and a Go `server/` — the ingestion pipeline, scoring engine, and 28-endpoint API. Its Go module is still named `github.com/samouraiworld/topofgnomes/server`, which is why Memba's docs refer to a `topofgnomes` repo that no longer resolves on GitHub: it's the old name of the same repo.

**What each fork actually took:**

| | Data pipeline | Analytics UI |
|---|---|---|
| **Reportz** | ✅ Inherited the full Go server (28 endpoints, GitHub GraphQL sync, scoring) | ❌ Inherited Gnolove's basic dashboard; added a broken landing page |
| **Memba** | ❌ None — every stat is fetched over HTTP from `backend.gnolove.world` | ✅ Built 16.6k LOC / 334 passing tests / 9 routes on top of it |

**Memba's `/gnolove` section is the asset nobody has reused.** It contains, none of which exists in Reportz:

- A **22-endpoint typed SDK** with ~50 Zod schemas validating every response boundary (`gnoloveApi.ts`, `gnoloveSchemas.ts`)
- **12 derived-analytics functions the upstream API does not provide** (`gnoloveAnalytics.ts`, 393 LOC + 276 LOC of tests): PR cycle-time histogram, topic heatmap, repo health matrix, **cohort retention grid**, **cross-team collaboration matrix**, sparklines
- URL-shareable, deep-linkable report state (`gnoloveReportUrl.ts`, 374 LOC)
- **CSV / Markdown / PDF export**
- 9 routes including `/analytics`, `/report`, `/notable-prs`, `/reports` (AI weekly narratives), per-contributor profiles with heatmaps
- 4,482 lines of dedicated CSS
- 334 passing tests + 3 Playwright specs

**So the real situation is:**

> Reportz has the engine and a weak dashboard. Memba has a beautiful dashboard and no engine. The merge that would have made Reportz a product was never performed.

That merge — porting Memba's analytics layer onto Reportz's pipeline, then making the pipeline multi-tenant — *is* the unbuilt product. It is also a far more tractable job than it looks, because both halves already exist and are known-good in isolation.

---

## 4. Honest summary

Reportz.dev is **not a project in progress**. It is a 40-minute architectural sketch from January that was left mid-refactor and hasn't been touched in six months. It doesn't compile, it has no data, no tests, no CI, no upstream remote, and its documentation describes a system (PostgreSQL, Redis, CLI flags, per-ecosystem pages) that was never built.

What it *does* have is a sound design instinct: the YAML → DB → API ecosystem model is the right shape, and the Go side is clean enough to pass `go vet` silently. The two hardest components — multi-ecosystem ingestion and stats aggregation — are the ones not started.

The gap between Reportz and Memba is not skill. Memba proves the capability is there. The gap is that Reportz received one evening and Memba received five months.
