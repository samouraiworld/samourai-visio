#!/usr/bin/env bash
set -euo pipefail
checker=${1:-"$(dirname "$0")/check-required-gates.py"}
python3 - "$checker" <<'PY'
import json
import subprocess
import sys

checker = sys.argv[1]


def case(label, value, expected_status, expected_text):
    payload = value if isinstance(value, str) else json.dumps(value)
    result = subprocess.run(
        [sys.executable, checker], input=payload, capture_output=True, text=True
    )
    if result.returncode != expected_status or expected_text not in result.stdout:
        raise SystemExit(
            f"FAIL: {label}: exit {result.returncode}; "
            f"wanted {expected_status} and {expected_text!r}; "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
    print(f"  ok  {label}")


success = {
    "metadata-attribution": {"result": "success"},
    "required-clauses": {"result": "success"},
}
case("both required gates succeeded", success, 0, "metadata and clause gates passed")
for gate in success:
    for state in ("failure", "cancelled", "skipped"):
        changed = {name: dict(value) for name, value in success.items()}
        changed[gate]["result"] = state
        case(
            f"{gate} {state} refuses",
            changed,
            1,
            f"required gates did not pass: {gate}",
        )
    changed = {name: dict(value) for name, value in success.items()}
    del changed[gate]
    case(
        f"{gate} missing refuses", changed, 1, f"required gates did not pass: {gate}"
    )
case("malformed JSON refuses", "{", 1, "invalid needs JSON")
case("empty input refuses", "", 1, "invalid needs JSON")
case("non-object JSON refuses", "[]", 1, "needs must be a JSON object")
case(
    "malformed gate result refuses",
    {"metadata-attribution": None, "required-clauses": {"result": "success"}},
    1,
    "required gates did not pass: metadata-attribution",
)
print("self-test passed: both successes and every failed, cancelled, skipped, missing or malformed gate")
PY
