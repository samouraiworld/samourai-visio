# Samouraï Visio icons

The v0.1 Visio glyph from the design of record: two overlapping participant
rings with a single cobalt `#2B4BDB` node at their meeting point, drawn on the
app-glyph grid — 24 units, a 1.8-unit white stroke, on a slate-900 `#2F3A45`
rounded-square tile at 25 % radius. One construction rule for the whole family,
exactly one cobalt node per app. The company keeps its circular badge.

| File | Replaces / used by |
|---|---|
| `favicon.ico` (16 + 32 + 48), `favicon-16x16.png`, `favicon-32x32.png` | the image's web-root favicons |
| `apple-touch-icon.png` (180) | iOS home-screen icon |
| `android-chrome-192x192.png`, `android-chrome-512x512.png` | PWA icons |
| `android-chrome-512x512-maskable.png` | PWA maskable icon (glyph inside the central 80 %) |
| `site.webmanifest` | names the app "Samouraï Visio" / "Visio" (upstream's manifest has empty names) |
| `logo.svg` | the in-room header logo, mounted over `/assets/logo.svg` (`Header.tsx`). This file is the v0.1 Visio glyph; `landing/logo-visio.svg` still carries the retired mark and is rebranded in its own change. |

Deploy: copy the directory to `custom/icons/` on the host and recreate the frontend (RUNBOOK §7). `compose.override.yaml` mounts each file individually — never a directory over `/assets`. `logo.svg` carries the accessible name "Samouraï Visio" in a `<title>`, which `preflight.sh public` greps for on the served file. nginx serves `/assets/*` with a 30-day cache, so returning visitors keep the previous in-room logo for up to a month after a deploy.

## Provenance

Every file here is generated from `design/v0.1/brand/glyphs/visio.svg` in the
design of record — the single source for the glyph's geometry and colour. No
colour is chosen here: the tile is slate-900, the node cobalt-500, and the
manifest's `theme_color` / `background_color` are the design's slate-900 and
frost-100 page surface.

Regenerate all sizes together whenever the glyph changes, and never edit a
raster by hand:

```
# render the glyph square and transparent at N pixels, then Lanczos-downsample
chrome --headless=new --default-background-color=00000000 \
       --force-device-scale-factor=1 --window-size=N,N --screenshot=out.png page.html
```

Each PNG is rendered at 16× the target size (8× at 512) and downsampled with a
Lanczos filter. The maskable 512 puts the glyph in the central 80 % on the
tile's own slate-900 field bled to the edges, because the platform mask crops
whatever falls outside the safe zone. `favicon.ico` packs the 16, 32 and 48
frames as PNG payloads.

Rasters carry no ancillary PNG chunks — only `IHDR`, `IDAT` and `IEND`. Icons
are published assets: they must not ship text, provenance or EXIF metadata.
