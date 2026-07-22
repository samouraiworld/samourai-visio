# Clerk Instance Audit — 2026-07-22

> Live audit of `clerk.samourai.app`, the identity provider shared by every
> `*.samourai.app` product. Read-only, via the unauthenticated `/v1/environment`
> endpoint that Clerk's own JS SDK uses. Re-runnable:
> `scripts/audit-clerk-instance.sh`.
>
> Commissioned to answer one question from [CTO_REVIEW §3.1](CTO_REVIEW_2026-07-22.md):
> **does this instance actually collect first and last name?**

## Verdict: it does not. Display names will be empty.

```
first_name   enabled=False  required=False
last_name    enabled=False  required=False
```

The email/password sign-up form does not ask for a name, so Clerk stores none,
so `userinfo` carries no `given_name` or `family_name` — and Meet computes:

```python
# django-lasuite src/lasuite/oidc_login/backends.py:292-296
full_name = " ".join(user_info[field] for field in name_fields if user_info.get(field))
return full_name or None
```

`full_name = None` for every user created through that form.

**This is the third independent way display names were going to break, and the
only one invisible from source.** The other two are fixed:

| # | Cause | Where found | Status |
|---|---|---|---|
| 1 | `usual_name` is a ProConnect claim Clerk never emits | upstream `settings.py:574` | fixed — override set |
| 2 | The override was written as JSON; `ListValue` splits on `,` | `configurations/values.py:238` | fixed — comma-separated |
| 3 | **The instance collects no names at all** | **this audit** | **open — needs a decision** |

Fixing 1 and 2 without 3 produces exactly the same user-visible result: nameless
participants. Anyone debugging it would check the scope and the env var — both
now correct — and find nothing wrong.

### Severity: degraded, not broken

`User.full_name` is `null=True, blank=True` (`core/models.py:175`), so nothing
crashes, and `AUTHENTICATED_PARTICIPANTS_CAN_EDIT_DISPLAY_NAME` defaults `True`,
so a participant can type their own name in-room. The failure is a poor first
impression — everyone arrives nameless — not an outage.

### One unknown, deliberately not guessed

`oauth_discord` and `oauth_github` are enabled and authenticatable. Clerk may
populate first/last name from an OAuth provider independently of what the
sign-up form collects. If it does, **display names would work for GitHub and
Discord users and not for email/password users** — intermittent, and it would
read as a Visio bug.

This cannot be settled from the environment endpoint. Settle it with one real
sign-up per method, checking `full_name` on the resulting user.

## Options

| | Approach | Cost |
|---|---|---|
| **A** | Enable `first_name` / `last_name` in Clerk | Changes the sign-up form for **Memba and Zentai** too. Every pre-existing user keeps a null name permanently. Needs an explicit decision — this is the shared instance marked "do not touch". |
| **B** | Point `OIDC_USERINFO_FULLNAME_FIELDS` at `email` | One line, no effect on other products. Participants show as `antoine@…` until they rename themselves. Leaks the full email address to everyone in the room — bad for a public service. |
| **C** | Accept null; rely on in-room rename | Zero config. Everyone joins nameless; the room UI lets them fix it. |
| **D** | Enable `username` in Clerk and use `preferred_username` | Same shared-form objection as A, but a username is a deliberate public handle rather than a legal name — arguably the better fit for a public video service. |

**Recommendation: D if you are willing to touch the shared form at all, otherwise C.**
B trades a cosmetic problem for a privacy one and should not ship on a public
instance. Whichever is chosen, settle the OAuth question above first — it may
mean the problem only affects a subset of users.

## Other findings

Not blocking, but they land squarely on decisions already open in the plan.

**`sign_up.mode = "public"`** — open signup, confirmed. Combined with the shared
org, this is the concrete form of the blast radius: any person on the internet
can create an account that is valid across every `*.samourai.app` product, not
only Visio. This is the fact that decision B1.8 turns on.

**`legal_consent_enabled = false`** — no terms or privacy acceptance at sign-up.
Clerk ships this natively. For a French public service with GDPR Art. 13
obligations and a CGU that must cover the shared-account behaviour, this is the
cheapest place to capture consent, and it is currently off.

**No abuse controls** — `block_disposable_email_domains`, `block_email_subaddresses`,
allowlist and blocklist are all disabled. For a free public WebRTC service with
no recording and unattributable ad-hoc rooms, disposable-email blocking is the
single cheapest lever available, and it is off.

**Reassuring:** `captcha_enabled = true` (smart widget), `email_address` is
required and used as the first factor, and no SAML/enterprise SSO is configured.

## Not changed

Nothing was modified. Every item above needs an owner decision, and the
instance is shared with two live products.
