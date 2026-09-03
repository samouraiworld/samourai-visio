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

sed -E "s/^INIT_HOLD=[0-9]+\$/INIT_HOLD=$HOLD/; s/^( *for _ in \\\$\\(seq 1 )30(\\); do)\$/\\1$POLL\\2/" \
  "$WORK/step.raw" > "$WORK/step.sh"
grep -qx "INIT_HOLD=$HOLD" "$WORK/step.sh" ||
  die "could not rewrite INIT_HOLD — its assignment changed shape"
grep -q "seq 1 $POLL" "$WORK/step.sh" ||
  die "could not rewrite the positive control's poll bound — its loop changed shape"

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
