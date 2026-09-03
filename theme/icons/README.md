# Samouraï Visio icons

**Status:** Accepted · **Owner:** zôÖma

The mark is two overlapping rings — two participants — with the cobalt node where they meet. Slate `#2F3A45` tile, white rings, cobalt `#2B4BDB` node, drawn on a 24-unit grid with a 6-unit corner radius. It comes from the design system v0.1 direction "Cobalt × Kodera — givre"; the vector source is `design/v0.1/brand/glyphs/visio.svg` in the internal pack.

There is no coral in this set. The earlier *Deux voix* glyph and its coral accent are retired along with the rest of the coral palette.

## Two marks, and why

| Size | Mark |
|---|---|
| 16, 32 | **One ring** around the node |
| 48 and up | **Two rings**, the full mark |

Below 48 the two rings cannot survive. They sit 5 units apart with radius 4.5, so they already overlap by more than half their width; at 16px one grid unit is 0.67 device pixels and the counter between them closes into a grey blur. A heavier stroke makes it worse, not better — that is the move the retired glyph used, and it worked there only because its rings were further apart.

16 and 32 are the same tab icon at two pixel densities. Splitting the mark between them would change the icon's identity between a standard and a retina display, so both carry the single ring: the same two elements, one participant fewer.

## Files

| File | Used by |
|---|---|
| `favicon.ico` (16 + 32 + 48), `favicon-16x16.png`, `favicon-32x32.png` | the image's web-root favicons |
| `apple-touch-icon.png` (180) | iOS home screen |
| `android-chrome-192x192.png`, `android-chrome-512x512.png` | PWA icons |
| `android-chrome-512x512-maskable.png` | PWA maskable icon; the mark sits inside the central 80 % safe zone |
| `site.webmanifest` | names the app "Samouraï Visio" / "Visio"; upstream's manifest has empty names |
| `logo.svg` | the in-room header logo, mounted over `/assets/logo.svg` (`Header.tsx`) |

## What a published raster may carry

Only `IHDR`, `IDAT` and `IEND`. These are published assets: they must not ship
text, provenance or EXIF metadata, which is how another party's attribution
travels into a repository unnoticed.

That is no longer only a statement here. The generator reads back every PNG it
writes, walks its chunks, and refuses to finish if a forbidden type is present
— and it prints the census, so the invariant is visible on every run rather
than asserted once in prose. It also checks that `favicon.ico` came out with
its three frames, because Pillow drops a requested size larger than the image
it is saving from and says nothing.

## Regenerating

```
python3 scripts/generate-icons.py theme/icons
```

Every raster comes from that script and nothing is drawn by hand, so the set is reproducible rather than archaeological. It needs only Pillow: the mark is four primitives — a rounded tile, the rings, the node — so it is drawn directly at 16× and downsampled with Lanczos rather than rasterised from SVG, and no SVG toolchain has to be installed to change an icon.

One trap the script documents in place: Pillow draws `ellipse(outline=…, width=…)` **inward** from the bounding box, while an SVG stroke straddles its path. Passing the path radius as the bounding box puts the ring a half-stroke too far in, which closes the counter between the two rings and fills the lens white. The bounding box has to be the outer edge, `r + w/2`.

Regenerate every size together if the geometry changes; the sizes are not independent.

Two things this does **not** cover. `landing/logo-visio.svg` still carries the
retired coral glyph and is not produced here. And the geometry now exists twice
— in `design/v0.1/brand/glyphs/visio.svg` and in this script's constants — with
nothing checking the two agree; a change to the vector source will not fail
anything here.

## Deploying

Copy the directory to `custom/icons/` on the host and recreate the frontend (RUNBOOK §7). `compose.override.yaml` mounts each file individually — never a directory over `/assets`.
