#!/usr/bin/env bash
# Self-test for the readiness assertions in the `Backup end-to-end` job's
# "And it WAITS for Postgres" step.
#
# THIS IS A STUB, AND A STUB IS A MODEL. The `docker` built below models the
# postgres entrypoint's two-phase startup — the Unix socket answering while
# initdb runs, TCP only once the real server has replaced it. It is not the
# entrypoint, and it knows nothing about postgres beyond that one behaviour.
#
# So this does NOT replace the slow-postgres run in `Backup end-to-end`. That
# run is the only thing here that tests the mechanism against the real image.
# Deleting it because this file exists would leave the mechanism untested and
# this fixture cheerfully green against its own imagination.
#
# What this DOES catch is the step's own failure branches rotting into checks
# that cannot fail — which has already happened twice in that step's short
# life, once when a timed threshold could be satisfied by a slow runner and
# once when the probe's positive control lived on a different source line.
# Every case below asserts the exit status AND the message, because a branch
# that exits non-zero while naming the wrong cause sends the next reader to
# the wrong place.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

STEP='And it WAITS for Postgres instead of racing its startup'
WORKFLOW=.github/workflows/ci.yml
# The step's two time constants, shrunk so the fixture runs in seconds. Both
# rewrites are asserted below: a silent miss would run the real 20s hold, or
# a 30-iteration poll, and quietly turn a fast fixture into a slow one.
HOLD=4
POLL=5

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

rc=0
ok()  { printf '  \033[32mok\033[0m   %s\n' "$1"; }
err() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; rc=1; }
die() { printf 'FAIL %s\n' "$1"; exit 1; }

echo "Drill readiness self-test — stub docker models the entrypoint, is not it"
echo

# ── Extract the step's real text, loudly ────────────────────────────────────
# A rename or a restructure must FAIL here. Silently extracting nothing would
# leave this fixture passing while exercising an empty string, which is the
# same class of defect it exists to catch.
awk -v want="      - name: $STEP" '
  $0 == want                          { in_step = 1; next }
  in_step && /^      - name: /        { exit }
  in_step && /^        run: \|/       { in_run = 1; next }
  in_run {
    if ($0 != "" && $0 !~ /^          /) exit
    sub(/^          /, "")
    print
  }
' "$WORKFLOW" > "$WORK/step.raw"

[ -s "$WORK/step.raw" ] ||
  die "no step named '$STEP' in $WORKFLOW — renamed or removed, and this fixture would otherwise test nothing"

for token in tcp_probe INIT_HOLD probe-check; do
  grep -q -- "$token" "$WORK/step.raw" ||
    die "the extracted step never mentions '$token' — it was restructured, and this fixture no longer exercises what it claims to"
done

# Each rewrite must have exactly ONE target. The sed patterns below are
# anchored to a shape, not to a line number, so a second line of the same
# shape would be rewritten too — and the difference check further down filters
# by shape, so it would accept both and stay silent. Counting the targets is
# what makes "a sed landing on a line it was not aimed at is reported" true,
# and unlike an inventory of time constants it needs no notion of what a
# constant is: it only asks how many lines each rewrite can reach.
# Both counts tolerate leading space, and deliberately match WIDER than the
# seds they guard. Wider is what keeps the rewrite guards downstream
# reachable: a line the sed cannot touch — an indented INIT_HOLD, a bound that
# is not literally 30 — is still counted here, so it survives to the rewrite
# guard and is reported there. A count pattern narrowed to its sed would make
# that guard dead code, which is how a check stops being able to fail.
n_hold="$(grep -cE '^ *INIT_HOLD=[0-9]+$' "$WORK/step.raw")"
n_poll="$(grep -cE '^ *for _ in \$\(seq 1 [0-9]+\); do$' "$WORK/step.raw")"
# Two different faults, two different messages. Zero targets means the shape
# changed and there is nothing to rewrite; more than one means every line of
# that shape gets rewritten, which shrinks more than the fixture means to.
if [ "$n_hold" -eq 0 ]; then
  die "the step has no INIT_HOLD=<number> line — the assignment changed shape, and this fixture cannot rewrite what it cannot find"
elif [ "$n_hold" -ne 1 ]; then
  die "the step carries $n_hold INIT_HOLD assignments — this fixture rewrites every line of that shape, so it would shrink more than it means to"
fi
if [ "$n_poll" -eq 0 ]; then
  die "the step has no literal 'seq 1 N' bound — the positive control's loop changed shape, and this fixture cannot rewrite what it cannot find"
elif [ "$n_poll" -ne 1 ]; then
  die "the step carries $n_poll literal 'seq 1 N' bounds — this fixture rewrites every line of that shape, so it would shrink more than it means to"
fi

sed -E "s/^INIT_HOLD=[0-9]+\$/INIT_HOLD=$HOLD/; s/^( *for _ in \\\$\\(seq 1 )30(\\); do)\$/\\1$POLL\\2/" \
  "$WORK/step.raw" > "$WORK/step.sh"
# Both guards anchored the same way. The poll bound was matched as a loose
# substring while INIT_HOLD was matched as a whole line, which would have
# accepted a rewrite that landed somewhere other than the line it was aimed at.
grep -qxF "INIT_HOLD=$HOLD" "$WORK/step.sh" ||
  die "could not rewrite INIT_HOLD — its assignment changed shape"
grep -qxF "for _ in \$(seq 1 $POLL); do" "$WORK/step.sh" ||
  die "could not rewrite the positive control's poll bound — its loop changed shape"

# Nothing but those two constants may differ, so the rewrite is provably
# surgical: if a sed ever lands on a line it was not aimed at, it is reported
# here rather than as a puzzling failure several cases later.
#
# Read the limit with the guarantee. This compares production against the
# fixture's copy, so it sees only what the REWRITE changed. A constant ADDED
# to the step is invisible to it — the new line is identical on both sides —
# and would still arrive disguised as a probe complaint. That is a legibility
# gap, not a safety one: an unrewritten constant either falls inside both
# holds and changes nothing, or outside the fixture's and fails a case, so it
# can only raise a false alarm and never let a defect through.
changed="$(diff "$WORK/step.raw" "$WORK/step.sh" | grep -E '^[<>]')"
unexpected="$(printf '%s\n' "$changed" |
  grep -vE '^[<>] (INIT_HOLD=[0-9]+|for _ in \$\(seq 1 [0-9]+\); do)$')"
if [ -n "$unexpected" ]; then
  die "the fixture's copy differs from the production step in more than the two constants it rewrites:
$unexpected"
fi
ok "fixture copy differs from production only in the two constants it rewrites"

# ── The stub docker ─────────────────────────────────────────────────────────
mkdir -p "$WORK/bin" "$WORK/tmp/visio" "$WORK/ws/scripts"
cat > "$WORK/bin/docker" <<STUB
#!/usr/bin/env bash
# Models one behaviour and no other: during init the Unix socket answers and
# TCP does not; after the hold, both do.
started=$WORK/started
hold=$HOLD
[ "\$1" = build ] && exit 0
[ "\$1" = rm ] && exit 0
if [ "\$1" = run ]; then date +%s > "\$started"; echo stub; exit 0; fi
if [ "\$1" = exec ]; then
  [ "\${STUB_EXEC_DELAY:-0}" -gt 0 ] && sleep "\$STUB_EXEC_DELAY"
  el=\$(( \$(date +%s) - \$(cat "\$started") ))
  case "\$*" in
    *"-h 127.0.0.1"*)
      case "\${STUB_TCP:-real}" in
        never)  exit 1 ;;
        always) exit 0 ;;
        *)      [ "\$el" -ge "\$hold" ] && exit 0 || exit 1 ;;
      esac ;;
    *pg_isready*)
      [ "\$el" -ge "\${STUB_SOCKET_AT:-1}" ] && exit 0 || exit 1 ;;
  esac
fi
exit 0
STUB
chmod +x "$WORK/bin/docker"

# A drill that takes longer than the hold, so the elapsed check passes for the
# right reason in the cases that reach it.
printf '#!/usr/bin/env bash\nsleep %s\necho "OK restored from local /stub/d.sql.gz into stub: 2 migrations, meet_user=2 meet_room=1"\n' \
  "$(( HOLD + 2 ))" > "$WORK/ws/scripts/restore-drill.sh"
chmod +x "$WORK/ws/scripts/restore-drill.sh"

# ── Cases ───────────────────────────────────────────────────────────────────
# run_case <label> <expected exit> <expected text> [VAR=value ...]
n=0
run_case() {
  local label="$1" want_code="$2" want_text="$3"
  shift 3
  local out code
  n=$(( n + 1 ))
  out="$WORK/out.$n"
  (
    cd "$WORK" || exit 1
    env PATH="$WORK/bin:$PATH" RUNNER_TEMP="$WORK/tmp" GITHUB_WORKSPACE="$WORK/ws" \
      "$@" bash "$WORK/step.sh"
  ) > "$out" 2>&1
  code=$?

  if [ "$code" -ne "$want_code" ]; then
    err "$label — exited $code, expected $want_code"
    sed 's/^/        /' "$out"
  elif ! grep -qF -- "$want_text" "$out"; then
    err "$label — exited $code as expected, but nothing said: $want_text"
    sed 's/^/        /' "$out"
  else
    ok "$label"
  fi
}

run_case "healthy: probes disagree in init, agree after" \
  0 "after the hold: the same probe succeeds"

run_case "MUTATION tcp_probe can never succeed — the vacuity hole" \
  1 "never succeeded even after the init hold" STUB_TCP=never

run_case "MUTATION TCP answers during init — upstream changed" \
  1 "probes no longer disagree" STUB_TCP=always

run_case "SLOW RUNNER the check overruns the hold before probing" \
  1 "left the ${HOLD}s hold" STUB_EXEC_DELAY=2

run_case "SLOW RUNNER the socket never answers inside the hold" \
  1 "never reported ready within the ${HOLD}s" STUB_SOCKET_AT=999

echo
if [ "$rc" -eq 0 ]; then
  echo "Drill readiness assertions all fire, and name the right cause."
else
  echo "Drill readiness self-test FAILED — an assertion no longer fires or misnames its cause."
fi
exit "$rc"
