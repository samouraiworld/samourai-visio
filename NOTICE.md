# Notices and attributions

## La Suite Meet

`visio.samourai.app` runs [**La Suite Meet**](https://github.com/suitenumerique/meet),
built by [DINUM](https://www.numerique.gouv.fr/) (Direction interministérielle du
numérique, France) and released under the MIT licence.

This repository contains **no fork of the application**. It carries deployment
configuration and a runtime theme; the application itself runs from unmodified
upstream container images (`lasuite/meet-backend`, `lasuite/meet-frontend`).

Two files here are **derived from** upstream templates and therefore redistribute
MIT-licensed material:

| File | Derived from |
|---|---|
| `deploy/env.d/common.example` | `env.d/production.dist/common` |
| `deploy/hosts.example` | `env.d/production.dist/hosts` |
| `deploy/livekit-server.yaml.example` | `docs/examples/livekit/server.yaml` |

The MIT licence text below is reproduced to satisfy the requirement that the
copyright notice and permission notice accompany substantial portions of the
software.

```
MIT License

Copyright (c) 2024 DINUM

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

> Verify the copyright line against upstream's own `LICENSE` before publishing —
> it is reproduced here from the upstream repository and the holder string
> should match exactly.

## No endorsement

"La Suite numérique", the Marianne logo and the French Republic's visual
identity are marks of the French State. Samouraï Coop is **not** affiliated with
or endorsed by DINUM or the French government.

Attribution ("Propulsé par La Suite Meet") is a statement of what the service
runs on. Do not present the service as an official or co-branded State product,
and do not enable `FRONTEND_USE_FRENCH_GOV_FOOTER`.

## Other components

| Component | Licence |
|---|---|
| [LiveKit](https://github.com/livekit/livekit) | Apache-2.0 |
| [PostgreSQL](https://www.postgresql.org/) | PostgreSQL Licence |
| [Redis](https://github.com/redis/redis) | RSALv2 / SSPLv1 (7.x) |
| [nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) | MIT |
| [Inter](https://rsms.me/inter/) | SIL Open Font Licence 1.1 |
