#!/usr/bin/env python3
"""Assert every brand colour pairing in theme/custom.css clears WCAG 2.1.

The Samourai palette is light: coral #FD6262 on white is 2.96:1, which fails
both AA text (4.5:1) and the non-text minimum (3:1). This guards against the
palette drifting back toward the raw brand values in a later edit.

Usage:  scripts/check-contrast.py [path/to/custom.css]
"""

import re
import sys
from pathlib import Path

# (token carrying the colour, token or literal it sits against, label, minimum)
# Minimums: 4.5 = WCAG 1.4.3 AA text; 3.0 = WCAG 1.4.11 non-text contrast.
PAIRINGS = [
    ("--colors-primary-800", "#FFFFFF", "primary button fill vs white text", 4.5),
    ("--colors-primary-800", "#FFFFFF", "link/border text on white bg", 4.5),
    ("--colors-primary", "#FFFFFF", "semantic primary vs primary-text", 4.5),
    ("--colors-primary-hover", "#FFFFFF", "primary hover vs white text", 4.5),
    ("--colors-primary-active", "#FFFFFF", "primary active vs white text", 4.5),
    ("--colors-primary-subtle-text", "#FFFFFF", "badge text on white", 4.5),
    ("--colors-primary-900", "#FFFFFF", "tertiary text on white", 4.5),
    ("--colors-focus-ring", "#FFFFFF", "focus ring on light surface", 3.0),
    ("--colors-focus-ring", "--colors-primary-dark-50", "focus ring in room", 3.0),
    ("--colors-primary-dark-100", "#FFFFFF", "in-room button vs white text", 4.5),
    ("--colors-primary-dark-300", "#FFFFFF", "in-room hover vs white text", 4.5),
    ("--colors-primary-dark-700", "--colors-primary-dark-100", "selected state (inverted)", 4.5),
    ("--colors-primary-dark-900", "--colors-primary-dark-100", "open select (inverted)", 4.5),
]


def relative_luminance(hex_colour: str) -> float:
    c = hex_colour.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    channels = [int(c[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def parse_tokens(css: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8})\s*;", css)
    }


def resolve(ref: str, tokens: dict[str, str]) -> str | None:
    return ref if ref.startswith("#") else tokens.get(ref)


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "theme/custom.css")
    if not path.is_file():
        print(f"FAIL  no such file: {path}", file=sys.stderr)
        return 1

    tokens = parse_tokens(path.read_text(encoding="utf-8"))
    if not tokens:
        print(f"FAIL  no colour tokens parsed from {path}", file=sys.stderr)
        return 1

    print(f"WCAG contrast — {path} ({len(tokens)} colour tokens)\n")
    failures = skipped = 0

    for fg_ref, bg_ref, label, minimum in PAIRINGS:
        fg, bg = resolve(fg_ref, tokens), resolve(bg_ref, tokens)
        if fg is None or bg is None:
            missing = fg_ref if fg is None else bg_ref
            print(f"  SKIP  {label:36} (token not set: {missing})")
            skipped += 1
            continue
        ratio = contrast(fg, bg)
        ok = ratio >= minimum
        failures += not ok
        print(
            f"  {'PASS' if ok else 'FAIL'}  {label:36} "
            f"{fg} on {bg}  {ratio:5.2f}:1  (min {minimum})"
        )

    print()
    if failures:
        print(f"{failures} pairing(s) below the WCAG minimum.")
        return 1
    print(f"All pairings clear WCAG 2.1.{f' {skipped} skipped.' if skipped else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
