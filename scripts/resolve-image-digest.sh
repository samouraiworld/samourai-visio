#!/usr/bin/env bash
# Resolve the digest a registry serves for an image tag — without Docker.
#
# Usage: scripts/resolve-image-digest.sh IMAGE:TAG
#   e.g. scripts/resolve-image-digest.sh lasuite/meet-backend:v1.24.0
#        scripts/resolve-image-digest.sh postgres:16      # library/ implied
#
# Prints `IMAGE:TAG@sha256:<64 hex>` — the exact line to paste as a
# service's `image:` in deploy/compose.override.yaml (RUNBOOK §10).
#
# The digest is the manifest LIST (index) digest: the one `docker pull`
# verifies on every platform, the one `docker compose config --images`
# shows, and the one Docker Hub's tag page lists. Per-platform manifests
# hang off it. It is read from the registry's own manifest endpoint
# (Docker-Content-Digest on a HEAD, RFC-style Accept for the OCI index and
# the Docker manifest list) rather than a local `docker images`, so the
# file records what the registry serves for that tag — not what some
# machine happened to have pulled once.

set -euo pipefail

ref="${1:?usage: $0 IMAGE:TAG}"
name="${ref%%:*}"
tag="${ref##*:}"
[ "$name" != "$ref" ] || { echo "FAIL $ref carries no tag" >&2; exit 1; }
case "$name" in
  */*) ;;
  *) name="library/$name" ;;
esac

token="$(curl -sSf "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${name}:pull" \
  | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
[ -n "$token" ] || { echo "FAIL no pull token for $name" >&2; exit 1; }

digest="$(curl -sSfI -H "Authorization: Bearer $token" \
  -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json' \
  "https://registry-1.docker.io/v2/${name}/manifests/${tag}" \
  | tr -d '\r' | awk 'tolower($1) == "docker-content-digest:" { print $2 }')"

if ! printf '%s\n' "$digest" | grep -qE '^sha256:[0-9a-f]{64}$'; then
  echo "FAIL no digest for $ref (registry answered '${digest:-nothing}')" >&2
  exit 1
fi
echo "${ref}@${digest}"
