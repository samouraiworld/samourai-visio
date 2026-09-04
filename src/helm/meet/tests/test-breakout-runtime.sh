#!/usr/bin/env bash
set -euo pipefail

chart_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "${test_dir}"' EXIT

deployment_document() {
  local manifest="$1"
  local deployment_name="$2"
  awk -v name="${deployment_name}" '
    BEGIN { RS = "---" }
    $0 ~ "kind: Deployment" && $0 ~ "name: " name { print; exit }
  ' "${manifest}"
}

assert_env_value() {
  local manifest="$1"
  local deployment_name="$2"
  local variable="$3"
  local expected="$4"
  deployment_document "${manifest}" "${deployment_name}" | awk \
    -v variable="${variable}" -v expected="${expected}" '
      $0 ~ "- name: \"" variable "\"" {
        getline
        if ($0 ~ "value: \"" expected "\"") found = 1
      }
      END { exit !found }
    '
}

default_manifest="${test_dir}/default.yaml"
helm template audit "${chart_dir}" > "${default_manifest}"
if grep -q "name: audit-meet-celery-beat" "${default_manifest}"; then
  echo "Celery Beat must stay disabled by default" >&2
  exit 1
fi
assert_env_value \
  "${default_manifest}" audit-meet-backend MEET_BREAKOUT_ROOMS_ENABLED false

enabled_manifest="${test_dir}/enabled-render.yaml"
helm template audit "${chart_dir}" \
  --set breakoutRooms.enabled=true \
  --set backend.envVars.CELERY_ENABLED.secretKeyRef.name=invalid-override \
  --set backend.envVars.CELERY_ENABLED.secretKeyRef.key=enabled \
  --set celeryBackend.envVars.CELERY_ENABLED=false \
  --set celeryBeat.envVars.CELERY_ENABLED.configMapKeyRef.name=invalid-override \
  --set celeryBeat.envVars.CELERY_ENABLED.configMapKeyRef.key=enabled \
  > "${enabled_manifest}"
for deployment in \
  audit-meet-backend \
  audit-meet-celery-backend \
  audit-meet-celery-beat
do
  assert_env_value \
    "${enabled_manifest}" "${deployment}" MEET_BREAKOUT_ROOMS_ENABLED true
  assert_env_value "${enabled_manifest}" "${deployment}" CELERY_ENABLED true
done

if helm template audit "${chart_dir}" \
  --set celeryBackend.envVars.MEET_BREAKOUT_ROOMS_ENABLED.secretKeyRef.name=legacy-flag \
  --set celeryBackend.envVars.MEET_BREAKOUT_ROOMS_ENABLED.secretKeyRef.key=enabled \
  > "${test_dir}/legacy-render.yaml" 2> "${test_dir}/legacy-error.txt"
then
  echo "Legacy component breakout flags must be rejected" >&2
  exit 1
fi
grep -q \
  "Use breakoutRooms.enabled instead of celeryBackend.envVars.MEET_BREAKOUT_ROOMS_ENABLED" \
  "${test_dir}/legacy-error.txt"

echo "Breakout Helm runtime invariants passed"
