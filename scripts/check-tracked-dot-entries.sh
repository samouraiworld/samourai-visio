#!/usr/bin/env bash
# Refuse any dot-named path component that nobody has vouched for.
#
# The defect this prevents: development tooling keeps local configuration in a
# dot-directory at the repository root. It is not ours, it is not in
# .gitignore, and one `git add .` commits it. This repository is public.
#
# Locally these directories are excluded through .git/info/exclude, which is
# per-clone and per-machine: it protects the one workstation it was typed on
# and no teammate's. This check travels with the repository, so it protects
# every clone.
#
# It is an allowlist. A denylist could only refuse the tools someone already
# thought of, and naming a tool's directory in a tracked file would publish
# exactly the string the exclusion exists to keep out. The allowlist names
# only what belongs here, so the unknown case is the refused case.
#
# Asserts on OUTPUT, not on grep exit codes: implementations disagree (ugrep
# exits 2 where GNU grep exits 1), which is the convention scripts/check-hygiene.sh
# already follows.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

allow_file="${DOT_ENTRIES_ALLOWLIST:-scripts/tracked-dot-entries.allow}"

if [ ! -r "$allow_file" ]; then
  echo "check-tracked-dot-entries: cannot read the allowlist at $allow_file. Refusing: an allowlist that is missing is not an allowlist that is empty, and treating it as empty would refuse every tracked dot-entry for the wrong reason." >&2
  exit 1
fi

# Comments and blank lines out; everything else is an entry.
mapfile -t allowed < <(grep -vE '^[[:space:]]*(#|$)' "$allow_file" | sed 's/[[:space:]]*$//')

if [ "${#allowed[@]}" -eq 0 ]; then
  echo "check-tracked-dot-entries: the allowlist at $allow_file declares no entries. Every repository here tracks at least .github and .gitignore, so an empty list means the file was emptied rather than that the repository changed." >&2
  exit 1
fi

files=$(git ls-files)
if [ -z "$files" ]; then
  echo "check-tracked-dot-entries: git ls-files reported no tracked files at all. Refusing rather than reporting a clean scan of nothing." >&2
  exit 1
fi

# Every dot-named component, at any depth: a tool directory nested under src/
# is the same defect as one at the root.
present=$(printf '%s\n' "$files" | tr '/' '\n' | grep '^\.' | sort -u)

unknown=""
while IFS= read -r entry; do
  [ -n "$entry" ] || continue
  printf '%s\n' "${allowed[@]}" | grep -qxF "$entry" || unknown="$unknown  $entry"$'\n'
done <<< "$present"

stale=""
for entry in "${allowed[@]}"; do
  [ -n "$entry" ] || continue
  printf '%s\n' "$present" | grep -qxF "$entry" || stale="$stale  $entry"$'\n'
done

rc=0

if [ -n "$unknown" ]; then
  echo "check-tracked-dot-entries: tracked dot-entry not on the allowlist:" >&2
  printf '%s' "$unknown" >&2
  echo "  A tool's local configuration directory must not be committed. If this entry genuinely belongs in version control, add it to $allow_file deliberately; if it was swept in by 'git add .', remove it from the index and exclude it locally." >&2
  rc=1
fi

if [ -n "$stale" ]; then
  echo "check-tracked-dot-entries: allowlist entry matching nothing tracked:" >&2
  printf '%s' "$stale" >&2
  echo "  A line that vouches for a path the repository no longer has is a stale excuse waiting to cover a future one. Remove it from $allow_file." >&2
  rc=1
fi

if [ "$rc" -eq 0 ]; then
  echo "check-tracked-dot-entries: ${#allowed[@]} allowed, $(printf '%s\n' "$present" | grep -c . ) tracked, none unvouched."
fi
exit "$rc"
