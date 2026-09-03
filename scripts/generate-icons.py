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

# A published raster carries image data and nothing else. Stated as the
# allowlist it is, not as a list of the metadata types thought of on the day:
# a denylist passed `pHYs` — which one `dpi=` argument is enough to write —
# and would have passed `tIME` and `iCCP` too, so the guard did not enforce
# the sentence above it.
ALLOWED_CHUNKS = {b"IHDR", b"IDAT", b"IEND"}

# The icon ships 16, 32 and 48.
ICO_FRAMES = 3


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


def mark_for(size):
    """Which mark a size carries. One place, so the boundary is testable."""
    return "full" if size >= FULL_MARK_FROM else "single"


def draw(size, inset=0.0, ground=True, mark=None):
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

    if (mark or mark_for(size)) == "single":
        # One ring around the node. Larger radius and heavier stroke than a
        # single ring of the full mark, because it is carrying the whole glyph.
        ring(12.0, 12.0, 6.0, 2.2)
        dot(12.0, 12.0, 2.2, COBALT)
    else:
        ring(9.5, 12.0, 4.5, 1.8)
        ring(14.5, 12.0, 4.5, 1.8)
        dot(12.0, 12.0, 1.6, COBALT)

    return img.resize((size, size), Image.LANCZOS)


def verify_png(path, name):
    """A published raster carries image data and nothing else."""
    found = census(path)
    extra = found - ALLOWED_CHUNKS
    if extra:
        raise SystemExit(f"{name} carries {', '.join(sorted(c.decode() for c in extra))}")
    return found


def verify_ico(path, name):
    """The icon carries all three frames, not just the one it was saved from."""
    with Image.open(path) as im:
        frames = sorted(im.info.get("sizes", []))
    if len(frames) != ICO_FRAMES:
        raise SystemExit(f"{name} has {len(frames)} frames, expected {ICO_FRAMES}")
    return frames


def check_boundary():
    """Prove the boundary size renders the full mark, not the small one.

    This is the regression that shipped: the comparison was `<=`, so 48 took
    the single-ring branch against the docstring, the README table and the
    body of the pull request — and nothing failed, because the only check was
    that the script reproduced its own output, which it did, wrongly.

    Restoring `<=` makes the two renders below identical and this raises.
    """
    if mark_for(FULL_MARK_FROM) != "full":
        raise SystemExit(
            f"{FULL_MARK_FROM}px must carry the full mark; the boundary "
            f"comparison is inverted")
    if mark_for(FULL_MARK_FROM - 1) != "single":
        raise SystemExit(f"{FULL_MARK_FROM - 1}px must carry the single ring")

    # Compared as bytes. The obvious alternative, differencing the two images
    # and asking for the bounding box of what changed, does not work here: on two
    # opaque RGBA images the difference has alpha 0 everywhere, so getbbox()
    # reports no difference for images that plainly differ — a comparison that
    # answers the wrong question, which is the mistake this whole file keeps
    # being about.
    if draw(FULL_MARK_FROM).tobytes() == draw(FULL_MARK_FROM, mark="single").tobytes():
        raise SystemExit(
            f"{FULL_MARK_FROM}px renders the same as the single-ring mark")


def main(out):
    check_boundary()
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
            found = verify_png(path, name)
            print(f"  {name:38s} {' '.join(sorted(c.decode() for c in found))}")
        else:
            frames = verify_ico(path, name)
            print(f"  {name:38s} {len(frames)} frames {frames}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
