FROM node:22-bookworm-slim AS node
FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM alpine/helm:3.19.0 AS helm
FROM python:3.13-slim-bookworm

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=helm /usr/bin/helm /usr/local/bin/helm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl ffmpeg gettext git libmagic1 build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir PyYAML==6.0.3
WORKDIR /workspace
ENV UV_LINK_MODE=copy
CMD ["python", "docker/ci/workflow.py"]
