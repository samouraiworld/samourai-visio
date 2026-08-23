# Samouraï Visio icons

The *Deux voix* glyph (chosen 2026-08-23): two participants overlapping, the lens-shaped overlap filled coral `#FD6262`, drawn on the app-logo family grid — a 24-unit grid, a 2-unit stroke, round caps, exactly one coral node per app. The company keeps its circular badge; every app gets a rounded-square tile. Docs, Greffon, Wesh, Memba and Zenao follow the same rule.

| File | Replaces / used by |
|---|---|
| `favicon.ico` (16 + 32 + 48), `favicon-16x16.png`, `favicon-32x32.png` | the image's web-root favicons |
| `apple-touch-icon.png` (180) | iOS home-screen icon |
| `android-chrome-192x192.png`, `android-chrome-512x512.png` | PWA icons |
| `android-chrome-512x512-maskable.png` | PWA maskable icon (glyph inside the central 80 %) |
| `site.webmanifest` | names the app "Samouraï Visio" / "Visio" (upstream's manifest has empty names) |
| `logo.svg` | the in-room header logo, mounted over `/assets/logo.svg` (`Header.tsx`); also `landing/logo-visio.svg` |

Deploy: copy the directory to `custom/icons/` on the host and recreate the frontend (RUNBOOK §7). `compose.override.yaml` mounts each file individually — never a directory over `/assets`. The small sizes (16/32/48) use a heavier 2.6-unit stroke so the rings stay closed.

Rasters are generated from the same geometry at 16× supersampling (PIL, Lanczos downsample); regenerate all sizes together if the glyph changes. Colour rules: white rings on dark surfaces, ink `#141416` rings on white with the WCAG-darkened accent `#B83636`; coral is never used as text on white.
