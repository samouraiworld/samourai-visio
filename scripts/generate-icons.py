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

SMALL_ABOVE = 48  # sizes at or below this use the single-ring mark


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

    if size <= SMALL_ABOVE:
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

    ico = [draw(s) for s in (16, 32, 48)]
    ico[0].save(os.path.join(out, "favicon.ico"),
                sizes=[(16, 16), (32, 32), (48, 48)], append_images=ico[1:])
    made.append("favicon.ico")

    for name in made:
        print(f"  {name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
