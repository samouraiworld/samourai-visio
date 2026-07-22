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
