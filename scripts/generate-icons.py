#!/usr/bin/env python3
"""Regenerate the Visio icon set from the v0.1 glyph geometry.

Four primitives on a 24-unit grid, drawn directly rather than rasterised from
SVG: a rounded tile, the rings, and the cobalt node. Drawn at 16x and
downsampled with Lanczos.

Two marks, not one. The full mark is two overlapping rings — two participants,
the node at their meeting. Below 48px those rings merge: they are 5 units apart
with radius 4.5, so at 16px one grid unit is 0.67 device pixels and the counter
between them closes. A heavier stroke makes that worse, not better. So 16 and 32
carry a single ring around the node — the same two elements, one participant
fewer — and the full mark returns at 48.
"""

import os
import sys

from PIL import Image, ImageDraw

SS = 16
GRID = 24.0
SLATE = (47, 58, 69, 255)
WHITE = (255, 255, 255, 255)
COBALT = (43, 75, 219, 255)

# The full two-ring mark returns AT this size; anything smaller carries the
# single ring. Named for the branch it opens rather than the one it closes,
# because the previous name invited an off-by-one and got one.
FULL_MARK_FROM = 48

# A published raster carries image data and nothing else. Text, provenance and
# EXIF chunks are how attribution travels into a repository unnoticed, so the
# absence is asserted after every save rather than left as a claim in prose.
FORBIDDEN_CHUNKS = (b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"caBX", b"dSIG")


def census(path):
    """The set of chunk types a PNG on disk actually carries."""
    raw = open(path, "rb").read()
    found, offset = set(), 8
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset:offset + 4], "big")
        kind = raw[offset + 4:offset + 8]
        found.add(kind)
        offset += 12 + length
        if kind == b"IEND":
            break
    return found


def draw(size, inset=0.0, ground=True):
    px = size * SS
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = px / GRID

    if ground:
        if inset:
            d.rectangle([0, 0, px, px], fill=SLATE)
        else:
            d.rounded_rectangle([0, 0, px - 1, px - 1], radius=6.0 * u, fill=SLATE)

    scale = 1.0 - inset
    off = px * inset / 2.0

    def at(x, y):
        return off + x * u * scale, off + y * u * scale

    def ring(cx, cy, r, w):
        # `r` is the path radius, as in the SVG, and the stroke straddles it.
        # PIL draws `outline` inward from the bounding box, so the box has to
        # be the OUTER edge — r + w/2 — or the ring sits a half-stroke too far
        # in and the counter between two overlapping rings closes.
        x, y = at(cx, cy)
        half = w / 2.0
        outer = (r + half) * u * scale
        d.ellipse([x - outer, y - outer, x + outer, y + outer], outline=WHITE,
                  width=max(1, round(w * u * scale)))

    def dot(cx, cy, r, fill):
        x, y = at(cx, cy)
        rr = r * u * scale
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill)

    if size < FULL_MARK_FROM:
        # One ring around the node. Larger radius and heavier stroke than a
        # single ring of the full mark, because it is carrying the whole glyph.
        ring(12.0, 12.0, 6.0, 2.2)
        dot(12.0, 12.0, 2.2, COBALT)
    else:
        ring(9.5, 12.0, 4.5, 1.8)
        ring(14.5, 12.0, 4.5, 1.8)
        dot(12.0, 12.0, 1.6, COBALT)

    return img.resize((size, size), Image.LANCZOS)


def main(out):
    os.makedirs(out, exist_ok=True)
    made = []
    for size, name in [(16, "favicon-16x16.png"), (32, "favicon-32x32.png"),
                       (180, "apple-touch-icon.png"),
                       (192, "android-chrome-192x192.png"),
                       (512, "android-chrome-512x512.png")]:
        draw(size).save(os.path.join(out, name))
        made.append(name)

    draw(512, inset=0.2).save(os.path.join(out, "android-chrome-512x512-maskable.png"))
    made.append("android-chrome-512x512-maskable.png")

    # Save from the LARGEST frame. Pillow silently drops any requested size
    # bigger than the image it is called on, so saving from the 16 px frame
    # produced a one-frame icon and no error — and comparing the script's
    # output with itself could never notice, because both sides were wrong.
    large, *smaller = [draw(s) for s in (48, 32, 16)]
    large.save(os.path.join(out, "favicon.ico"),
               sizes=[(48, 48), (32, 32), (16, 16)], append_images=smaller)
    made.append("favicon.ico")

    for name in made:
        path = os.path.join(out, name)
        if name.endswith(".png"):
            found = census(path)
            bad = [c.decode() for c in FORBIDDEN_CHUNKS if c in found]
            if bad:
                raise SystemExit(f"{name} carries {', '.join(bad)}")
            print(f"  {name:38s} {' '.join(sorted(c.decode() for c in found))}")
        else:
            with Image.open(path) as im:
                frames = sorted(im.info.get("sizes", []))
            if len(frames) != 3:
                raise SystemExit(f"{name} has {len(frames)} frames, expected 3")
            print(f"  {name:38s} {len(frames)} frames {frames}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
