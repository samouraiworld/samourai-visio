#!/usr/bin/env bash
# Prove check-tracked-dot-entries.sh can fail, and fail for the reason it says.
#
# Each case asserts the MESSAGE, not the exit code. Exit 1 is also what a typo
# in the script produces, so a self-test reading only the status stays green
# after the check has quietly stopped checking.
#
# The cases build throwaway repositories and stage files into them. Staging is
# enough -- `git ls-files` reads the index -- so nothing here commits.
#
# The final count is computed from the passes, not written as a literal. A
# hardcoded "N cases OK" is a number that goes stale the first time someone
# deletes a case, and it goes stale silently -- reporting a coverage the file
# no longer has.
set -uo pipefail

here="$(git rev-parse --show-toplevel)"
check="$here/scripts/check-tracked-dot-entries.sh"
work="$(mktemp -d)"
fails=0
passes=0

cleanup() { [ -n "${work:-}" ] && [ -d "$work" ] && rm -r "$work"; }
trap cleanup EXIT

# scaffold <name> <allowlist-lines...> — a repo with .github and .gitignore staged
scaffold() {
  local name="$1"; shift
  local d="$work/$name"
  mkdir -p "$d/scripts" "$d/.github"
  git -C "$d" init -q
  : > "$d/.gitignore"
  : > "$d/.github/keep"
  printf '%s\n' "$@" > "$d/scripts/tracked-dot-entries.allow"
  git -C "$d" add -A >/dev/null 2>&1
  printf '%s' "$d"
}

# expect_fail_saying <dir> <substring> [env-assignments...]
expect_fail_saying() {
  local dir="$1" want="$2"; shift 2
  local out rc
  out=$(cd "$dir" && env "$@" bash "$check" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then
    echo "FAIL: expected a refusal, got exit 0"; printf '%s\n' "$out" | sed 's/^/    /'
    fails=$((fails+1)); return
  fi
  if ! grep -qF "$want" <<<"$out"; then
    echo "FAIL: refused, but not for the stated reason."
    echo "  wanted: $want"
    printf '%s\n' "$out" | sed 's/^/    /'
    fails=$((fails+1)); return
  fi
  passes=$((passes+1)); echo "ok: refused saying \"$want\""
}

# --- case 1: a tool directory swept in by `git add .` ------------------------
# The defect itself. A dot-directory nobody vouched for is staged; the check
# must name it rather than report a clean scan.
d=$(scaffold sweptin .github .gitignore)
mkdir -p "$d/.sometool"; : > "$d/.sometool/settings.json"
git -C "$d" add -A >/dev/null 2>&1
expect_fail_saying "$d" "tracked dot-entry not on the allowlist" IGNORE=1
out=$(cd "$d" && bash "$check" 2>&1)
if grep -qF ".sometool" <<<"$out"; then
  passes=$((passes+1)); echo "ok: the offending entry is named in the message"
else
  echo "FAIL: refused without naming the offending entry"; fails=$((fails+1))
fi

# --- case 2: nested, not at the root -----------------------------------------
# A tool directory under src/ is the same defect. A root-only scan would miss it.
d=$(scaffold nested .github .gitignore)
mkdir -p "$d/src/.sometool"; : > "$d/src/.sometool/settings.json"
git -C "$d" add -A >/dev/null 2>&1
expect_fail_saying "$d" "tracked dot-entry not on the allowlist" IGNORE=1

# --- case 3: a stale allowlist line ------------------------------------------
# An entry vouching for a path the repository no longer has is an excuse in
# waiting: leave it and it silently covers the next thing to take that name.
d=$(scaffold stale .github .gitignore .departed)
expect_fail_saying "$d" "allowlist entry matching nothing tracked" IGNORE=1

# --- case 4: the allowlist is gone -------------------------------------------
# Missing must not be read as empty. Read as empty, the check would refuse
# every tracked dot-entry and be deleted for crying wolf within a week.
d=$(scaffold missing .github .gitignore)
rm "$d/scripts/tracked-dot-entries.allow"
expect_fail_saying "$d" "cannot read the allowlist" IGNORE=1

# --- case 5: the allowlist is emptied ----------------------------------------
# Distinct from missing, and the likelier accident: a bad edit truncates it.
d=$(scaffold emptied "# only a comment")
expect_fail_saying "$d" "declares no entries" IGNORE=1

# --- case 6: the real repository is accepted ---------------------------------
# A check that refuses everything is not a check.
if out=$(cd "$here" && bash "$check" 2>&1); then
  if grep -q "none unvouched" <<<"$out"; then
    passes=$((passes+1)); echo "ok: the real repository is accepted -- $out"
  else
    echo "FAIL: accepted, but without reporting what it scanned"; fails=$((fails+1))
  fi
else
  echo "FAIL: the real repository was refused"; printf '%s\n' "$out" | sed 's/^/    /'; fails=$((fails+1))
fi

if [ $fails -ne 0 ]; then
  echo "check-tracked-dot-entries.selftest: $fails case(s) failed"
  exit 1
fi
echo "check-tracked-dot-entries.selftest: $passes cases OK"
