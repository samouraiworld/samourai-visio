"""Seed disposable meetings and ordinary Django sessions, never HTTP bypasses."""

import json
import os
from pathlib import Path

from core.models import ResourceAccess, RoleChoices, Room, User
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore


def seed_user(name):
    user = User(sub=f"e2e-{name}", full_name=name, language="en-us")
    user.set_unusable_password()
    user.save()
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return user, {"identity": user.sub, "cookie": session.session_key}


result = {}
for index, scenario in enumerate(("lifecycle", "retry", "private", "timer")):
    code = f"eaa-aaaa-aa{chr(ord('a') + index)}"
    owner, login = seed_user(f"{scenario}-host")
    room = Room.objects.create(
        name=code,
        slug=code,
        access_level="restricted" if scenario == "private" else "public",
    )
    ResourceAccess.objects.create(resource=room, user=owner, role=RoleChoices.OWNER)
    result[scenario] = {"roomId": str(room.pk), "slug": room.slug, "owner": login}
_, result["outsider"] = seed_user("outsider")
Path(os.environ.get("E2E_SEED_PATH", "/artifacts/seed.json")).write_text(
    json.dumps(result), encoding="utf-8"
)
