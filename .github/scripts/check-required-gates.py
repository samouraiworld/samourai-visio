#!/usr/bin/env python3
"""Make the existing required status depend on both policy jobs."""

import json
import sys

EXPECTED = ("metadata-attribution", "required-clauses")


def main():
    try:
        results = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"::error::invalid needs JSON: {error}")
        return 1

    if not isinstance(results, dict):
        print("::error::needs must be a JSON object")
        return 1

    bad = [
        name
        for name in EXPECTED
        if not isinstance(results.get(name), dict)
        or results[name].get("result") != "success"
    ]
    if bad:
        print("::error::required gates did not pass: " + ", ".join(bad))
        return 1

    print("metadata and clause gates passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
