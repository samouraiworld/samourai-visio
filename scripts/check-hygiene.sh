#!/usr/bin/env bash
# Repo hygiene gate. Every check here corresponds to a defect that actually
# reached this repository once — see docs/CTO_REVIEW_2026-07-22.md.
#
# docs/ is excluded from the forbidden-string checks: the analysis documents
# legitimately quote the wrong names while explaining why they are wrong.
# Without that exclusion the gate could never pass, and a gate that cannot
# pass gets deleted.
#
# Asserts on OUTPUT, never on grep exit codes — implementations differ
# (ugrep exits 2 where GNU grep exits 1).

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

fail=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=1; }

# check <label> <grep-output>  — non-empty output means failure
check() {
  local label="$1" out="$2"
  if [ -z "$out" ]; then pass "$label"; else
    bad "$label"; printf '        %s\n' "$out" | sed 's/$//'
  fi
}

# Tracked files that are neither documentation nor the gates themselves.
# scripts/ is excluded for the same reason docs/ is: these files necessarily
# contain every pattern they search for, so scanning them is self-defeating.
mapfile -t SRC < <(git ls-files | grep -vE '^(docs|scripts)/' || true)

echo "Repo hygiene"
echo

# ── Dead / wrong configuration names ────────────────────────────────────────
check "no FRONTEND_CSS_URL (the real setting is FRONTEND_CUSTOM_CSS_URL)" \
  "$(grep -n 'FRONTEND_CSS_URL' "${SRC[@]}" 2>/dev/null | grep -v 'FRONTEND_CUSTOM_CSS_URL' || true)"

# Matches a DECLARATION (`--c--theme--x: value`), not prose explaining that
# these names are dead — the theme file and the runbook both say so on purpose.
check "no Cunningham token declarations (Meet uses Panda CSS)" \
  "$(grep -nE -- '--c--theme--[a-z0-9-]+ *:' "${SRC[@]}" 2>/dev/null || true)"

# ── JSON-shaped list values ─────────────────────────────────────────────────
# values.ListValue splits on ',' and never parses JSON. Brackets become part
# of the value and the setting silently does nothing.
check "no bracketed list env values (ListValue splits on ',' — JSON never parses)" \
  "$(grep -nE '^[A-Z][A-Z0-9_]*=\[' "${SRC[@]}" 2>/dev/null || true)"

# ── Placeholders that must never reach a real config ────────────────────────
# Config files only. Markdown legitimately quotes these while explaining which
# upstream defaults must be replaced and why.
mapfile -t CFG < <(git ls-files 'deploy/*' 'theme/*' | grep -v '\.md$' || true)
check "no unfilled upstream placeholders in tracked config" \
  "$(grep -nE 'mail@yourdomain\.tld|<your livekit secret key>|<generate a secret key>' \
      "${CFG[@]}" 2>/dev/null || true)"

# ── Secrets ─────────────────────────────────────────────────────────────────
# Real Clerk/Resend/LiveKit credentials, never the <angle-bracket> hints in
# the .example templates.
check "no live-looking credentials in tracked files" \
  "$(grep -nE '(sk_live_|sk_test_|pk_live_|re_[A-Za-z0-9]{20,}|APIKey[A-Za-z0-9]{16,})' \
      "${SRC[@]}" 2>/dev/null || true)"

check "no secret-bearing files tracked" \
  "$(git ls-files | grep -E '(^|/)\.env($|\.)|(^|/)env\.d/(common|postgresql)$|\.(pem|key)$|(^|/)secrets/' || true)"

check "no database dumps or runtime data tracked" \
  "$(git ls-files | grep -E '\.(sql|dump|sql\.gz|aof|rdb)$|(^|/)data/|(^|/)backups?/' || true)"

# ── .gitignore actually covers the paths the runbook creates ────────────────
uncovered=""
for p in deploy/.env deploy/.env.prod deploy/env.d/common deploy/env.d/postgresql \
         deploy/env.d/backup \
         deploy/data/databases/backend/PG_VERSION deploy/data/redis/appendonly.aof \
         deploy/secrets/django_secret_key backup.sql backups/meet.sql.gz \
         deploy/compose.yaml deploy/livekit-server.yaml; do
  git check-ignore -q "$p" || uncovered="$uncovered$p"$'\n'
done
check ".gitignore covers every runtime, secret and backup path" "${uncovered%$'\n'}"

# ── Licensing: this repo redistributes MIT-derived upstream files ───────────
for f in LICENSE NOTICE.md; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    pass "$f is tracked"
  else
    bad "$f is missing — this repo redistributes MIT-licensed upstream files"
  fi
done

# ── No third-party resource reaches a visitor's browser ─────────────────────
# The service claims, on its own public pages, that it loads nothing from a
# third party. That claim has to be enforced, not remembered: a font @import
# in theme/custom.css already leaked every visitor's IP and User-Agent to a CDN
# once (audit 2026-07-24), on every page of the app including inside rooms.
#
# Scans the files that are actually delivered to browsers, for anything that
# fetches from an origin we do not control. Anchors on the URL-bearing CSS/HTML
# constructs only — ordinary <a href> links are fine, they are navigation the
# visitor chooses, not an automatic request.
ext=""
for f in theme/custom.css $(git ls-files 'landing/*.html' 'landing/*.css'); do
  [ -f "$f" ] || continue
  # strip comments so documentation about the rule cannot trip the rule
  stripped=$(sed -e 's|/\*.*\*/||g' -e '/\/\*/,/\*\//d' -e 's|<!--.*-->||g' -e '/<!--/,/-->/d' "$f")
  # Absolute URLs on OUR OWN origin are first-party by definition and fetch
  # nothing off-host. They are also unavoidable: og:image and rel=canonical
  # must be absolute, because every social platform resolves them against its
  # own origin rather than the page's. Dropped AFTER matching, so the pattern
  # stays blunt and any other host still fails.
  hits=$(printf '%s\n' "$stripped" | grep -nEo \
    '@import[^;]*https?://[^;]*|<(script|iframe)[^>]+src="https?://[^"]+|<link[^>]+href="https?://[^"]+|url\(["'"'"']?https?://[^)]+' \
    | grep -v 'https://visio\.samourai\.app' || true)
  [ -n "$hits" ] && ext="$ext$f: $hits"$'\n'
done
check "no third-party resource is loaded by the theme or the landing pages" "${ext%$'\n'}"

# ── Legal pages exist and name the publisher ────────────────────────────────
# Upstream's own /mentions-legales and /conditions-utilisation declare DINUM as
# publisher, with the French State's SIREN and a serving public official as
# publication director. They are hardcoded React components — no env var
# overrides them — so this service must ship its own, and must never link to
# theirs. Both halves are checked.
legal=""
for f in landing/mentions-legales/index.html landing/confidentialite/index.html \
         landing/conditions-utilisation/index.html; do
  [ -s "$f" ] || legal="$legal$f is missing or empty"$'\n'
done

# ── Share card: the asset every social platform crops to ────────────────────
# A share of this service must not unfurl as DINUM's product. Two halves, each
# useless alone: the 1200x630 file has to exist (below ~600px wide, platforms
# fall back to the site icon — which is upstream's), and the page has to point
# at it absolutely, because every platform resolves og:image against its own
# origin rather than the page's.
card=""
if [ -s landing/og-card.png ]; then
  dim="$(python3 -c 'from PIL import Image;im=Image.open("landing/og-card.png");print("%dx%d"%im.size)' 2>/dev/null \
        || python3 -c 'import struct;d=open("landing/og-card.png","rb").read(24);print("%dx%d"%struct.unpack(">II",d[16:24]))')"
  [ "$dim" = "1200x630" ] || card="${card}landing/og-card.png is $dim, expected 1200x630"$'\n'
else
  card="${card}landing/og-card.png is missing — shares fall back to upstream's icon"$'\n'
fi
grep -q 'property="og:image" content="https://visio.samourai.app/accueil/og-card.png"' landing/index.html ||
  card="${card}landing/index.html does not point og:image at the absolute og-card.png URL"$'\n'
grep -q 'name="twitter:card" content="summary_large_image"' landing/index.html ||
  card="${card}landing/index.html is not requesting a large twitter card"$'\n'
# og:url must name the page that describes THIS service. Pointing it at the
# site root sends crawlers to upstream's SPA shell, titled "LaSuite Meet".
grep -q 'property="og:url" content="https://visio.samourai.app/accueil/"' landing/index.html ||
  card="${card}og:url does not point at /accueil/ — a crawler re-fetching it lands on upstream's shell"$'\n'
check "share card is ours, present at 1200x630, and referenced absolutely" "${card%$'\n'}"
[ -s landing/mentions-legales/index.html ] &&
  grep -q "830 485 108" landing/mentions-legales/index.html ||
  legal="${legal}landing/mentions-legales/index.html does not carry Samouraï Coop's SIREN"$'\n'
badlink=$(grep -rlE 'href="/(mentions-legales|conditions-utilisation)' landing/ 2>/dev/null || true)
[ -n "$badlink" ] && legal="${legal}links to upstream's DINUM legal pages: $badlink"$'\n'
check "legal pages are ours, and nothing links to upstream's" "${legal%$'\n'}"

# ── Scripts stay executable and syntactically valid ─────────────────────────
badsh=""
for s in $(git ls-files 'scripts/*.sh'); do
  [ -x "$s" ] || badsh="$badsh$s (not executable)"$'\n'
  bash -n "$s" 2>/dev/null || badsh="$badsh$s (syntax error)"$'\n'
done
check "shell scripts are executable and parse" "${badsh%$'\n'}"

echo
[ "$fail" -eq 0 ] && echo "Hygiene clean." || echo "Hygiene FAILED."
exit "$fail"
