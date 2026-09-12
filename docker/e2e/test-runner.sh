#!/usr/bin/env bash
# Fault injection proves failures survive log collection and resource cleanup.
set -euo pipefail
repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
test_directory=$(mktemp -d "${TMPDIR:-/tmp}/visio-e2e-runner-test.XXXXXX")
trap 'rm -rf "$test_directory"' EXIT
mkdir -p "$test_directory/bin"
cat > "$test_directory/bin/docker" <<'DOCKER'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
command_name=$6
if [[ "$command_name" == "${FAIL_COMMAND:-}" ]]; then
  exit 17
fi
DOCKER
chmod +x "$test_directory/bin/docker"

run_case() {
  local name=$1 expected=$2 failure=${3:-}
  mkdir -p "$test_directory/$name"
  local result=0
  PATH="$test_directory/bin:$PATH" \
    FAKE_DOCKER_LOG="$test_directory/$name/commands.log" \
    FAIL_COMMAND="$failure" E2E_ARTIFACTS_DIR="$test_directory/$name/artifacts" \
    "$repository_root/bin/test-e2e-local" --grep 'literal argument' \
    > "$test_directory/$name/output.log" 2>&1 || result=$?
  if [[ "$result" != "$expected" ]]; then
    cat "$test_directory/$name/output.log"
    echo "$name returned $result; expected $expected" >&2
    exit 1
  fi
  local commands
  commands=$(cat "$test_directory/$name/commands.log")
  if [[ "$commands" != *"logs --no-color"* ||
        "$commands" != *"down --volumes --remove-orphans"* ]]; then
    echo "$name did not collect logs and clean up" >&2
    exit 1
  fi
}

run_case success 0
run_case failing-browser 17 run
run_case failing-build 17 build
run_case failing-startup 17 up
run_case failing-cleanup 1 down
printf '%s\n' 'E2E runner fault-injection checks passed.'
