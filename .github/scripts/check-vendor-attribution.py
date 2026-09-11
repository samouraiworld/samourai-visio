#!/usr/bin/env python3
"""Fail if a tracked file carries assistant-vendor attribution.

AGENTS.md: the name of the assistant that helped build this never appears in a
samouraiworld repository. The recursive case-insensitive grep that rule
prescribes misses the two ways it has actually arrived here:

  1. Binary metadata. `grep -I` skips binaries, and PNG provenance lives in an
     ancillary chunk, so a whole icon set can carry attribution invisibly.
  2. Base64. A provenance manifest embedded in an SVG holds the name encoded,
     so it is not present as text at all and no plain grep can see it.

So this reads every tracked file as bytes, decodes base64 runs, and inflates
compressed PNG text chunks.

It also fails on the metadata containers themselves, whoever wrote them: a
design asset has no reason to carry a text or provenance chunk, and checking
only for today's vendor name would miss tomorrow's. Competitor product names
are NOT flagged — naming Microsoft Copilot in a pricing benchmark is
legitimate research. What is forbidden is attribution of the assistant used to
produce the work.
"""

import base64
import os
import re
import subprocess
import sys
import zlib

# The needles are hex-encoded rather than written out, because this file is
# itself a tracked file: spelled plainly, the check would flag its own source
# and could never pass. Decoded, they read as the assistant vendor names.
VENDOR = tuple(
    bytes.fromhex(h)
    for h in (
        "616e7468726f706963",  # the company
        "636c61756465",  # the assistant
    )
)

# The provenance manifest namespace, searched as text anywhere in a file —
# that is how it appears in an SVG.
NAMESPACE = tuple(
    bytes.fromhex(h)
    for h in (
        "63327061",  # manifest namespace
    )
)

# Ancillary PNG chunks that can hold arbitrary text, including a manifest
# re-added under another name. These are recognised only at a real chunk
# boundary inside a real PNG, never as a substring: their four letters are
# ordinary words in prose (and in this file), and matching them loosely would
# flag every document that discusses image internals.
FORBIDDEN_CHUNKS = tuple(
    bytes.fromhex(h)
    for h in (
        "63614258",  # provenance
        "69545874",  # international text
        "74455874",  # text
        "7a545874",  # compressed text
        "65584966",  # exif
        "64534947",  # signature
    )
)

# 40 characters decode to 30 bytes — short enough to catch a name tucked into a
# small blob. The earlier threshold of 120 let a 96-character run through.
B64_RUN = re.compile(rb"[A-Za-z0-9+/=]{40,}")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Chunks whose payload is zlib-compressed. The third is an embedded colour
# profile: a legitimate chunk type, which is exactly why it is here. The other
# two are forbidden outright, so inflating them can never be the only reason a
# file is caught — without a permitted compressed chunk in this list, the
# inflation path could break and no test would notice.
COMPRESSED_CHUNKS = (
    bytes.fromhex("7a545874"),  # compressed text
    bytes.fromhex("69545874"),  # international text
    bytes.fromhex("69434350"),  # colour profile
)

ALLOWLIST = os.path.join(os.path.dirname(__file__), "vendor-attribution-allowlist.txt")


def load_allowlist():
    if not os.path.exists(ALLOWLIST):
        return set()
    keep = set()
    for line in open(ALLOWLIST, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if line:
            keep.add(line)
    return keep


def png_chunks(raw):
    """Yield (type, body) for each chunk of a PNG. Nothing if not a PNG."""
    if not raw.startswith(PNG_SIGNATURE):
        return
    offset = len(PNG_SIGNATURE)
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset : offset + 4], "big")
        kind = raw[offset + 4 : offset + 8]
        body = raw[offset + 8 : offset + 8 + length]
        offset += 12 + length
        yield kind, body
        if kind == b"IEND":
            return


def inflate(body):
    """Decompress a compressed text chunk payload, or return nothing.

    A name inside one of these is neither readable text nor base64, so it
    would otherwise pass both of the other scans.
    """
    # Skip the keyword and the compression flags, then inflate what is left.
    _, _, tail = body.partition(b"\0")
    for start in range(min(len(tail), 4) + 1):
        try:
            return zlib.decompress(tail[start:])
        except zlib.error:
            continue
    return None


def findings(path):
    with open(path, "rb") as handle:
        raw = handle.read()

    hits = []

    def note(label):
        if label not in hits:
            hits.append(label)

    def scan(payload, suffix=""):
        # Matched case-insensitively: these are words, and capitalisation
        # carries no meaning in them.
        low = payload.lower()
        for needle in VENDOR + NAMESPACE:
            if needle in low:
                note(needle.decode() + suffix)

    scan(raw)

    for run in B64_RUN.findall(raw):
        padded = run + b"=" * (-len(run) % 4)
        try:
            decoded = base64.b64decode(padded, validate=False)
        except Exception:
            continue
        scan(decoded, " (base64)")

    for kind, body in png_chunks(raw):
        if kind in FORBIDDEN_CHUNKS:
            note(kind.decode() + " chunk")
        if kind in COMPRESSED_CHUNKS:
            blob = inflate(body)
            if blob is not None:
                scan(blob, " (compressed chunk)")

    return sorted(set(hits))


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    allow = load_allowlist()
    listing = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    bad = {}
    for blob in listing.split(b"\0"):
        if not blob:
            continue
        rel = blob.decode("utf-8", "surrogateescape")
        if rel in allow:
            continue
        try:
            hits = findings(os.path.join(root, rel))
        except OSError:
            continue
        if hits:
            bad[rel] = hits

    for rel, hits in sorted(bad.items()):
        print(f"::error file={rel}::carries {', '.join(hits)}")
    if bad:
        print(
            f"\n{len(bad)} tracked files carry attribution or metadata that "
            f"should not be published."
        )
        print(
            "Strip it. The allowlist exempts a whole file from every needle, "
            "so it is a last resort, not a fix."
        )
        return 1
    print("no tracked file carries assistant attribution")
    return 0


if __name__ == "__main__":
    sys.exit(main())
