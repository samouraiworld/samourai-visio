#!/usr/bin/env python3
"""Build the Samourai (Clerk-backed) Greffon catalog entry for Visio.

Mirrors the exact validated structure of greffon-catalog's existing visio/1.0
entry, but swaps the bundled Keycloak demo for the external Clerk org, drops
recording (MinIO/Celery) from v1, and injects our theme. Emits metadata.json.
"""
import base64, json, pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "deploy/greffon/visio/1.0"
OUT.mkdir(parents=True, exist_ok=True)


def b64(s: str, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(s.encode()).decode()


# ── Gateway nginx: single public origin -> frontend / backend / livekit ──────
# No /identity (Clerk is external), no /media (no recording in v1).
# X-Forwarded-Proto is set to https authoritatively here — the gateway always
# sits behind Greffon's TLS, so it never trusts a client-supplied value.
GATEWAY = r"""
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 8083;
    server_name _;
    charset utf-8;
    client_max_body_size 100M;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
    location /admin/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
    location /static/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }

    # LiveKit signaling (WebSocket). Trailing slash strips the /livekit prefix
    # so the client's /livekit/rtc reaches livekit:7880/rtc.
    location /livekit/ {
        proxy_pass http://livekit:7880/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 86400;
    }

    location / {
        proxy_pass http://frontend:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
"""

# ── LiveKit: single-port UDP mux published as the L4 port (Jinja-rendered) ───
LIVEKIT = """port: 7880
bind_addresses:
  - "0.0.0.0"
rtc:
  # Single UDP media port, published directly on the host as the L4 port.
  # advertise (node_ip) == listen (udp_port) == public, in proxy and tunnel mode.
  udp_port: {{ instance_l4_port }}
  use_external_ip: false
  node_ip: {{ instance_l4_host }}
  enable_loopback_candidate: false
keys:
  meet: "{{ config.LIVEKIT_API_SECRET }}"
webhook:
  api_key: meet
  urls:
    - http://gateway:8083/api/v1.0/rooms/webhooks-livekit/
logging:
  level: info
  json: false
"""

theme_css = (REPO / "theme/custom.css").read_text()


def secret(title, key, containers, minlen, alnum=False):
    return {
        "title": title,
        "schema": {
            "type": "object",
            "required": ["value"],
            "properties": {
                "value": {
                    "type": "string", "title": title, "writeOnly": True,
                    "minLength": minlen,
                    "format": "greffon-secret-alnum" if alnum else "greffon-secret",
                }
            },
            "x-greffon-visibility": "advanced",
        },
        "default_value": {"value": ""},
        "destinations": [{"type": "env", "container": c, "key": k} for c, k in containers],
    }


def user_input(title, key, container, env_key, description, secret_field=False):
    prop = {"type": "string", "title": title, "description": description}
    if secret_field:
        prop["writeOnly"] = True
    return {
        "title": title,
        "schema": {
            "type": "object", "required": ["value"],
            "properties": {"value": prop},
            "x-greffon-visibility": "visible",
        },
        "default_value": {"value": ""},
        "destinations": [{"type": "env", "container": container, "key": env_key}],
    }


metadata = {
    "name": "Samouraï Visio",
    "min_greffer_version": "0.3.3",
    "logo": "https://raw.githubusercontent.com/samouraiworld/samourai-visio/main/theme/icons/android-chrome-512x512.png",
    "description": (
        "Free video conferencing by Samouraï Coop — La Suite Meet (DINUM), "
        "themed and authenticated against the Samouraï Clerk SSO. Guests join by "
        "link with no account. WebRTC media uses one UDP port published on the "
        "host. Requires: a Clerk OAuth application whose redirect URI is set to "
        "{{ instance_url }}/api/v1.0/callback/, and this instance bound to a "
        "stable domain. No recording in v1."
    ),
    "categories": ["productivity", "collaboration"],
    "images": [],
    "ports": [
        {"name": "gateway_8083", "exposure_tier": "http", "protocol": "tcp"},
        {"name": "livekit_7882", "exposure_tier": "l4", "protocol": "udp",
         "same_port": True, "udp_reviewed": True},
    ],
    "configurations": [
        {
            "title": "Gateway routing config",
            "schema": {"type": "object", "properties": {
                "file": {"type": "string", "format": "data-url", "title": "nginx gateway default.conf"}},
                "x-greffon-visibility": "hidden"},
            "default_value": {"file": b64(GATEWAY, "text/plain")},
            "destinations": [{"type": "file", "volume": "gateway_conf", "name": "default.conf"}],
        },
        {
            "title": "LiveKit config",
            "schema": {"type": "object", "properties": {
                "file": {"type": "string", "format": "data-url", "title": "livekit.yaml"}},
                "x-greffon-visibility": "hidden"},
            "default_value": {"file": b64(LIVEKIT, "text/plain")},
            "destinations": [{"type": "file", "volume": "livekit_conf", "name": "livekit.yaml",
                              "x-greffon-render": True}],
        },
        {
            "title": "Samouraï theme",
            "schema": {"type": "object", "properties": {
                "file": {"type": "string", "format": "data-url", "title": "custom style.css"}},
                "x-greffon-visibility": "hidden"},
            "default_value": {"file": b64(theme_css, "text/css")},
            "destinations": [{"type": "file", "volume": "frontend_custom", "name": "style.css"}],
        },
        secret("Django secret key", "DJANGO_SECRET_KEY", [("backend", "DJANGO_SECRET_KEY")], 50),
        secret("Database password", "DB_PASSWORD",
               [("backend", "DB_PASSWORD"), ("postgresql", "POSTGRES_PASSWORD")], 24),
        secret("LiveKit API secret", "LIVEKIT_API_SECRET", [("backend", "LIVEKIT_API_SECRET")], 32),
        user_input("Clerk client ID", "OIDC_RP_CLIENT_ID", "backend", "OIDC_RP_CLIENT_ID",
                   "From the Clerk OAuth application. Register redirect URI "
                   "{{ instance_url }}/api/v1.0/callback/ and scopes 'openid email profile'."),
        user_input("Clerk client secret", "OIDC_RP_CLIENT_SECRET", "backend", "OIDC_RP_CLIENT_SECRET",
                   "Shown once in the Clerk dashboard when the OAuth app is created.",
                   secret_field=True),
        {
            "title": "SMTP",
            "schema": {"type": "object", "properties": {}},
            "default_value": {},
            "destinations": [
                {"type": "smtp", "container": "backend", "key": k} for k in (
                    "DJANGO_EMAIL_HOST", "DJANGO_EMAIL_PORT", "DJANGO_EMAIL_HOST_USER",
                    "DJANGO_EMAIL_HOST_PASSWORD", "DJANGO_EMAIL_FROM",
                    "DJANGO_EMAIL_USE_TLS", "DJANGO_EMAIL_USE_SSL")
            ],
        },
    ],
}

(OUT / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
print("wrote", OUT / "metadata.json", f"({(OUT / 'metadata.json').stat().st_size} bytes)")
print("configurations:", len(metadata["configurations"]))
