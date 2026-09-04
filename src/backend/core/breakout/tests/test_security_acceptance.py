# pylint: disable=missing-function-docstring,redefined-outer-name,protected-access
"""Executable security and privacy acceptance tests for breakout rooms."""

from unittest import mock

from django.apps import apps

import pytest
from rest_framework.test import APIClient

from core.breakout.models import BreakoutAssignment, BreakoutSession
from core.breakout.tests.factories import BreakoutRoomFactory, BreakoutSessionFactory
from core.factories import RoomFactory, UserFactory
from core.models import RoomAccessLevel
from core.services.lobby import LobbyService

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def breakout_settings(settings):
    settings.MEET_BREAKOUT_ROOMS_ENABLED = True
    settings.CELERY_ENABLED = True
    settings.LOBBY_COOKIE_NAME = "breakout-guest"
    settings.LOBBY_KEY_PREFIX = "breakout-security-test"
    settings.SECRET_KEY = "breakout-security-test-secret"


def admit_guest(client, room, username="Guest"):
    with mock.patch(
        "core.utils.generate_livekit_config",
        return_value={"token": "main-token"},
    ):
        response = client.post(
            f"/api/v1.0/rooms/{room.id}/request-entry/",
            {"username": username},
            format="json",
        )
    assert response.status_code == 200
    return response


def active_assignment(room, identity, name="Guest"):
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)
    BreakoutAssignment.objects.create(
        breakout_room=breakout_room,
        participant_identity=identity,
        participant_name=name,
    )
    return session, breakout_room


def test_guest_cookie_is_not_the_public_participant_identity():
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    response = admit_guest(APIClient(), room)
    cookie_name = LobbyService._get_guest_cookie_name(room.id)

    assert response.cookies[cookie_name].value != response.json()["id"]
    assert response.cookies[cookie_name]["httponly"] is True
    assert response.cookies[cookie_name]["secure"] is True


def test_visible_identity_cannot_be_replayed_to_join_victims_breakout():
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    victim = APIClient()
    victim_entry = admit_guest(victim, room, "Victim")
    victim_identity = victim_entry.json()["id"]
    session, breakout_room = active_assignment(room, victim_identity, "Victim")
    join_url = (
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/"
        f"rooms/{breakout_room.id}/join/"
    )

    attacker = APIClient()
    attacker.cookies.load(
        {LobbyService._get_guest_cookie_name(room.id): victim_identity}
    )
    with mock.patch("core.utils.generate_token", return_value="stolen-token"):
        response = attacker.post(
            join_url,
            {"participant_id": victim_identity, "username": "Victim"},
            format="json",
        )

    assert response.status_code == 403


def test_valid_guest_joins_without_supplying_identity_or_name():
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    guest = APIClient()
    entry = admit_guest(guest, room, "Alice")
    session, breakout_room = active_assignment(room, entry.json()["id"], "Alice")

    with mock.patch("core.utils.generate_token", return_value="breakout-token"):
        response = guest.post(
            f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/"
            f"rooms/{breakout_room.id}/join/",
            {},
            format="json",
        )

    assert response.status_code == 200
    assert response.json()["livekit"]["token"] == "breakout-token"


def test_guest_capability_is_scoped_to_each_parent_room():
    client = APIClient()
    first_room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    second_room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)

    first = admit_guest(client, first_room)
    first_cookie_name = LobbyService._get_guest_cookie_name(first_room.id)
    second_cookie_name = LobbyService._get_guest_cookie_name(second_room.id)
    first_cookie = client.cookies[first_cookie_name].value
    second = admit_guest(client, second_room)

    assert first_cookie_name != second_cookie_name
    assert client.cookies[first_cookie_name].value == first_cookie
    assert client.cookies[second_cookie_name].value != first_cookie
    assert first.json()["id"] != second.json()["id"]


def test_guest_capability_for_one_room_cannot_authenticate_in_another():
    first_room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    second_room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    first_client = APIClient()
    first = admit_guest(first_client, first_room)
    first_cookie = first_client.cookies[
        LobbyService._get_guest_cookie_name(first_room.id)
    ].value
    session, breakout_room = active_assignment(
        second_room, first.json()["id"], "Victim"
    )
    attacker = APIClient()
    attacker.cookies.load(
        {LobbyService._get_guest_cookie_name(second_room.id): first_cookie}
    )

    response = attacker.post(
        f"/api/v1.0/rooms/{second_room.id}/breakout-sessions/{session.id}/"
        f"rooms/{breakout_room.id}/join/",
        {},
        format="json",
    )

    assert response.status_code == 403


def test_guest_requests_help_without_caller_supplied_identity():
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    guest = APIClient()
    entry = admit_guest(guest, room, "Alice")
    session, breakout_room = active_assignment(room, entry.json()["id"], "Alice")

    with mock.patch("core.breakout.services.utils.notify_participants"):
        response = guest.post(
            f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/request-help/",
            {},
            format="json",
        )

    assert response.status_code == 201
    help_request = apps.get_model("core", "BreakoutHelpRequest").objects.get()
    assert help_request.requester_identity == entry.json()["id"]
    assert help_request.requester_name == "Alice"
    assert help_request.breakout_room_id == breakout_room.id


def test_participant_assignment_endpoint_returns_only_the_caller():
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    guest = APIClient()
    entry = admit_guest(guest, room, "Alice")
    session, breakout_room = active_assignment(room, entry.json()["id"], "Alice")
    other_room = BreakoutRoomFactory(session=session)
    BreakoutAssignment.objects.create(
        breakout_room=other_room,
        participant_identity="other-participant",
        participant_name="Other",
    )

    response = guest.get(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/current-assignment/"
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": str(session.id),
        "revision": session.revision,
        "status": "active",
        "started_at": session.started_at,
        "ends_at": session.ends_at,
        "duration_seconds": session.duration_seconds,
        "assignment": {
            "breakout_room_id": str(breakout_room.id),
            "breakout_room_name": breakout_room.name,
            "livekit_room_name": breakout_room.livekit_room_name,
        },
        "help_request": None,
    }
    assert "other-participant" not in str(response.json())


def test_authenticated_identity_cannot_be_overridden_by_request_body():
    room = RoomFactory(access_level=RoomAccessLevel.PUBLIC)
    user = UserFactory(sub="real-user")
    session, breakout_room = active_assignment(room, "victim-user", "Victim")
    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/"
        f"rooms/{breakout_room.id}/join/",
        {"participant_id": "victim-user", "username": "Victim"},
        format="json",
    )

    assert response.status_code == 403
