#!/usr/bin/env bash
# Audit the live Clerk instance's public configuration.
#
# NOT a CI gate — this reads the production identity provider shared by every
# *.samourai.app product, and CI should not poll it. Run it by hand before a
# deploy, and after any change in the Clerk dashboard.
#
# It reads /v1/environment, the same unauthenticated endpoint Clerk's own JS
# SDK reads to render the sign-in widget. No credentials, no writes.
#
# Why it exists: the OIDC discovery document advertises which claims Clerk CAN
# emit. It says nothing about which attributes this INSTANCE actually collects.
# The `profile` scope is necessary but not sufficient — if first_name and
# last_name are disabled, userinfo carries no given_name/family_name and every
# display name in Meet renders empty, no matter how the env vars are written.
#
# Usage:  scripts/audit-clerk-instance.sh [clerk-host]

set -uo pipefail

HOST="${1:-${CLERK_HOST:-clerk.samourai.app}}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

note() { printf '  \033[33mNOTE\033[0m  %s\n' "$1"; }
good() { printf '  \033[32m OK \033[0m  %s\n' "$1"; }
warn() { printf '  \033[31mWARN\033[0m  %s\n' "$1"; }

echo "Clerk instance audit — ${HOST}"
echo

code=$(curl -sS -o "$WORK/env.json" -w '%{http_code}' \
  "https://${HOST}/v1/environment?__clerk_api_version=2025-04-10&_clerk_js_version=5.0.0")
if [ "$code" != "200" ]; then
  warn "GET /v1/environment -> HTTP $code (expected 200)"
  exit 1
fi

python3 - "$WORK/env.json" <<'PY'
import json, sys

env = json.load(open(sys.argv[1]))
us = env.get("user_settings", {})
attrs = us.get("attributes", {})
signup = us.get("sign_up", {})
restr = us.get("restrictions", {})

GOOD, NOTE, WARN = "  \033[32m OK \033[0m  ", "  \033[33mNOTE\033[0m  ", "  \033[31mWARN\033[0m  "


def enabled(name):
    return bool(attrs.get(name, {}).get("enabled"))


print("Display names (Meet's OIDC_USERINFO_FULLNAME_FIELDS)")
first, last = enabled("first_name"), enabled("last_name")
if first and last:
    print(GOOD + "first_name and last_name are collected -> given_name/family_name will arrive")
else:
    print(WARN + f"first_name enabled={first}, last_name enabled={last}")
    print("        The sign-up form does not collect names, so userinfo carries no")
    print("        given_name/family_name and Meet's full_name will be NULL for every")
    print("        user created through it. The `profile` scope does not change this.")

social = [k for k, v in us.get("social", {}).items() if isinstance(v, dict) and v.get("enabled")]
if social and not (first and last):
    print(NOTE + f"OAuth providers enabled: {', '.join(social)}")
    print("        These may populate names independently of the sign-up form, so display")
    print("        names could work for some users and not others. Verify with one real")
    print("        signup per method before concluding either way.")

print()
print("Signup exposure")
mode = signup.get("mode")
print((NOTE if mode == "public" else GOOD) + f"sign_up.mode = {mode}")
if mode == "public":
    print("        Anyone can create an account. On a shared org that account is valid")
    print("        across every *.samourai.app product, not just Visio.")
print((GOOD if signup.get("captcha_enabled") else WARN)
      + f"captcha_enabled = {signup.get('captcha_enabled')} ({signup.get('captcha_widget_type')})")
print((GOOD if signup.get("legal_consent_enabled") else WARN)
      + f"legal_consent_enabled = {signup.get('legal_consent_enabled')}")
if not signup.get("legal_consent_enabled"):
    print("        No terms/privacy acceptance at sign-up. Clerk ships this natively.")

print()
print("Abuse controls")
for key, label in (("block_disposable_email_domains", "disposable email domains"),
                   ("block_email_subaddresses", "email subaddresses (user+tag@)"),
                   ("allowlist", "allowlist"),
                   ("blocklist", "blocklist")):
    on = bool(restr.get(key, {}).get("enabled"))
    print((GOOD if on else NOTE) + f"{label}: {'enabled' if on else 'not enabled'}")

print()
print("Authentication factors")
for name in sorted(attrs):
    a = attrs[name]
    if a.get("enabled"):
        bits = [k for k in ("required", "used_for_first_factor", "used_for_second_factor")
                if a.get(k)]
        print(f"        {name:16} {', '.join(bits) or 'optional'}")
PY

echo
echo "Read-only audit. Nothing was modified."
