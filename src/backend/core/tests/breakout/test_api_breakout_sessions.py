"""
Test breakout sessions API endpoints in the Meet core app.
"""

# pylint: disable=W0621,W0613
import asyncio
import json
from unittest import mock

from django.conf import settings
from django.core import signing
from django.db import IntegrityError
from django.http import HttpRequest

import jwt
import pytest
from livekit.api import TwirpError
from rest_framework.test import APIClient

from core import models
from core.breakout import services
from core.factories import RoomFactory, UserFactory, UserResourceAccessFactory
from core.services.lobby import LobbyService

pytestmark = pytest.mark.django_db

ACTIVE = models.BreakoutSessionStatusChoices.ACTIVE
CLOSED = models.BreakoutSessionStatusChoices.CLOSED


@pytest.fixture
def livekit():
    """A media server client whose main room is live with some metadata."""
    client = mock.MagicMock()
    client.aclose = mock.AsyncMock()
    client.room.create_room = mock.AsyncMock()
    client.room.delete_room = mock.AsyncMock()
    client.room.update_room_metadata = mock.AsyncMock()
    client.room.list_rooms = mock.AsyncMock(
        return_value=mock.Mock(
            rooms=[mock.Mock(metadata=json.dumps({"access_level": "public"}))]
        )
    )
    with mock.patch.object(
        services.utils, "create_livekit_client", return_value=client
    ):
        yield client


@pytest.fixture
def owner_room():
    """A meeting and an API client logged in as its owner."""
    room = RoomFactory(configuration={"can_publish_sources": ["microphone"]})
    user = UserFactory()
    UserResourceAccessFactory(resource=room, user=user, role="owner")
    client = APIClient()
    client.force_login(user)
    return room, client


def url(room, suffix=""):
    """The breakout sessions URL of a meeting."""
    return f"/api/v1.0/rooms/{room.id!s}/breakout-sessions/{suffix}"


def payload(*room_participants):
    """A split with one room per list of identities."""
    return {
        "rooms": [
            {
                "name": f"Room {index + 1}",
                "participants": [
                    {"identity": identity, "name": identity.title()}
                    for identity in identities
                ],
            }
            for index, identities in enumerate(room_participants)
        ]
    }


def make_session(room, *room_participants):
    """Rows of an active session, without the media server."""
    session = models.BreakoutSession.objects.create(room=room)
    for index, identities in enumerate(room_participants):
        breakout_room = models.BreakoutRoom.objects.create(
            session=session,
            name=f"Room {index + 1}",
            livekit_room_name=f"breakout_{session.id!s}_{index}",
        )
        for identity in identities:
            models.BreakoutAssignment.objects.create(
                session=session, breakout_room=breakout_room, identity=identity
            )
    return session


def written_metadata(livekit):
    """The metadata of the last write to the main room."""
    request = livekit.room.update_room_metadata.await_args.args[0]
    return json.loads(request.metadata)


def guest_client(room):
    """A guest's client carrying a signed capability, and its identity in the room."""
    cookie = signing.dumps("capability", salt=LobbyService.GUEST_COOKIE_SALT)
    client = APIClient()
    client.cookies[settings.LOBBY_COOKIE_NAME] = cookie
    replay = HttpRequest()
    replay.COOKIES[settings.LOBBY_COOKIE_NAME] = cookie
    return client, LobbyService.get_or_create_participant_id(replay, room.id)


# Create


def test_api_breakout_sessions_create_owner(livekit, owner_room):
    """The owner opens rooms on the media server, then rows, then the signal."""
    room, client = owner_room

    response = client.post(url(room), payload(["alice"], ["bob", "carol"]), "json")

    assert response.status_code == 201
    session = models.BreakoutSession.objects.get()
    assert session.status == ACTIVE
    assert response.json()["rooms"] == [
        {
            "id": str(breakout_room.id),
            "name": breakout_room.name,
            "participants": [
                {"identity": a.identity, "name": a.name}
                for a in breakout_room.assignments.all()
            ],
        }
        for breakout_room in session.rooms.all()
    ]
    assert [r["name"] for r in response.json()["rooms"]] == ["Room 1", "Room 2"]
    created = [call.args[0] for call in livekit.room.create_room.await_args_list]
    assert sorted(request.name for request in created) == [
        f"breakout_{session.id!s}_0",
        f"breakout_{session.id!s}_1",
    ]
    assert all(request.empty_timeout == 300 for request in created)
    assert written_metadata(livekit) == {
        "access_level": "public",
        "breakout": {"session_id": str(session.id), "status": "active"},
    }
    livekit.room.delete_room.assert_not_awaited()


@pytest.mark.parametrize("role", [None, "member"])
def test_api_breakout_sessions_create_not_manager(livekit, role):
    """Only the meeting's owner or administrators open a session."""
    room = RoomFactory()
    client = APIClient()
    if role:
        user = UserFactory()
        UserResourceAccessFactory(resource=room, user=user, role=role)
        client.force_login(user)

    response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == (401 if role is None else 403)
    assert not models.BreakoutSession.objects.exists()
    livekit.room.create_room.assert_not_awaited()


@pytest.mark.parametrize(
    "rooms",
    [
        [["alice"]],
        [[f"p{index}"] for index in range(11)],
        [["alice"], ["alice"]],
    ],
)
def test_api_breakout_sessions_create_invalid(livekit, owner_room, rooms):
    """Two to ten rooms, and one room per participant."""
    room, client = owner_room

    response = client.post(url(room), payload(*rooms), "json")

    assert response.status_code == 400
    livekit.room.create_room.assert_not_awaited()


def test_api_breakout_sessions_create_already_active(livekit, owner_room):
    """A second session is refused before the media server is called."""
    room, client = owner_room
    make_session(room, ["alice"])

    response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == 409
    livekit.room.create_room.assert_not_awaited()


def test_api_breakout_sessions_create_media_server_fails(livekit, owner_room):
    """A room the media server refuses deletes the others and leaks nothing."""
    room, client = owner_room
    livekit.room.create_room.side_effect = [
        None,
        TwirpError("internal", "dial tcp livekit.internal:7880", status=500),
    ]

    response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == 503
    assert "livekit.internal" not in response.content.decode()
    assert livekit.room.delete_room.await_count == 2
    assert not models.BreakoutSession.objects.exists()


def test_api_breakout_sessions_create_rows_fail(livekit, owner_room):
    """Rows that cannot be written delete the media server rooms."""
    room, client = owner_room

    with mock.patch.object(
        models.BreakoutAssignment.objects, "bulk_create", side_effect=IntegrityError
    ):
        response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == 409
    assert livekit.room.delete_room.await_count == 2
    assert not models.BreakoutSession.objects.exists()


@pytest.mark.parametrize("main_room_live", [True, False])
def test_api_breakout_sessions_create_signal_fails(livekit, owner_room, main_room_live):
    """Without the signal nobody moves, so the session is undone."""
    room, client = owner_room
    if main_room_live:
        livekit.room.update_room_metadata.side_effect = TimeoutError
    else:
        livekit.room.list_rooms.return_value = mock.Mock(rooms=[])

    response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == 503
    assert livekit.room.delete_room.await_count == 2
    assert not models.BreakoutSession.objects.exists()


def test_api_breakout_sessions_create_signal_times_out_after_landing(
    livekit, owner_room
):
    """A signal write that times out is taken back, in case it landed."""
    room, client = owner_room
    livekit.room.update_room_metadata.side_effect = [TimeoutError, None]

    response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == 503
    assert livekit.room.update_room_metadata.await_count == 2
    assert written_metadata(livekit) == {"access_level": "public"}
    assert not models.BreakoutSession.objects.exists()


def test_api_breakout_sessions_create_races_another_open(livekit, owner_room):
    """An Open landing during this one's media server calls wins; this one is undone."""
    room, client = owner_room
    run = services._run  # pylint: disable=protected-access
    competing = []

    def run_then_compete(step, *args):
        result = run(step, *args)
        if step is services._create_rooms:  # pylint: disable=protected-access
            competing.append(make_session(room, ["carol"]))
        return result

    with mock.patch.object(services, "_run", side_effect=run_then_compete):
        response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == 409
    created = {c.args[0].name for c in livekit.room.create_room.await_args_list}
    deleted = {c.args[0].room for c in livekit.room.delete_room.await_args_list}
    assert len(created) == 2 and deleted == created
    assert list(models.BreakoutSession.objects.all()) == competing
    livekit.room.update_room_metadata.assert_not_awaited()


def test_api_breakout_sessions_media_server_call_is_bounded(livekit, owner_room):
    """A media server that never answers costs one deadline, not a worker."""
    room, client = owner_room

    async def hang(*args, **kwargs):
        await asyncio.sleep(60)

    livekit.room.create_room.side_effect = hang
    livekit.room.delete_room.side_effect = hang

    with mock.patch.object(services, "MEDIA_SERVER_TIMEOUT_SECONDS", 0.05):
        response = client.post(url(room), payload(["alice"], ["bob"]), "json")

    assert response.status_code == 503
    assert not models.BreakoutSession.objects.exists()


# List


def test_api_breakout_sessions_list(livekit, owner_room):
    """The owner reads the active session only."""
    room, client = owner_room
    make_session(room, ["alice"])
    models.BreakoutSession.objects.update(status=CLOSED)
    session = make_session(room, ["alice"], ["bob"])

    response = client.get(url(room))

    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == [str(session.id)]
    assert [
        [p["identity"] for p in r["participants"]] for r in response.json()[0]["rooms"]
    ] == [["alice"], ["bob"]]


def test_api_breakout_sessions_list_empty_and_member(livekit, owner_room):
    """No session reads as an empty list, and a member reads nothing."""
    room, client = owner_room
    assert client.get(url(room)).json() == []

    member = UserFactory()
    UserResourceAccessFactory(resource=room, user=member, role="member")
    client.force_login(member)
    assert client.get(url(room)).status_code == 403


# Close


def test_api_breakout_sessions_close(livekit, owner_room):
    """Close removes the signal, deletes the rooms, and a second close answers 200."""
    room, client = owner_room
    session = make_session(room, ["alice"], ["bob"])

    response = client.post(url(room, f"{session.id!s}/close/"))

    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    session.refresh_from_db()
    assert session.status == CLOSED
    assert session.closed_at is not None
    assert written_metadata(livekit) == {"access_level": "public"}
    assert sorted(
        call.args[0].room for call in livekit.room.delete_room.await_args_list
    ) == [f"breakout_{session.id!s}_0", f"breakout_{session.id!s}_1"]

    livekit.reset_mock()
    assert client.post(url(room, f"{session.id!s}/close/")).status_code == 200
    livekit.room.delete_room.assert_not_awaited()


def test_api_breakout_sessions_close_room_already_gone(livekit, owner_room):
    """A room the media server already dropped counts as deleted."""
    room, client = owner_room
    session = make_session(room, ["alice"], ["bob"])
    livekit.room.delete_room.side_effect = TwirpError("not_found", "gone", status=404)

    response = client.post(url(room, f"{session.id!s}/close/"))

    assert response.status_code == 200


def test_api_breakout_sessions_close_fails(livekit, owner_room):
    """A failed delete keeps the session active, so closing again retries."""
    room, client = owner_room
    session = make_session(room, ["alice"], ["bob"])
    livekit.room.delete_room.side_effect = TwirpError(
        "internal", "livekit.internal refused", status=500
    )

    response = client.post(url(room, f"{session.id!s}/close/"))

    assert response.status_code == 503
    assert "livekit.internal" not in response.content.decode()
    session.refresh_from_db()
    assert session.status == ACTIVE


@pytest.mark.parametrize("main_room_live", [True, False])
@mock.patch.object(LobbyService, "clear_room_cache")
def test_api_breakout_sessions_close_lobby_admissions(
    mock_clear, livekit, owner_room, main_room_live
):
    """Admissions kept for a meeting that ended during the session go at close."""
    room, client = owner_room
    session = make_session(room, ["alice"], ["bob"])
    if not main_room_live:
        livekit.room.list_rooms.return_value = mock.Mock(rooms=[])

    response = client.post(url(room, f"{session.id!s}/close/"))

    assert response.status_code == 200
    if main_room_live:
        mock_clear.assert_not_called()
    else:
        mock_clear.assert_called_once_with(room.id)


def test_api_breakout_sessions_close_member(livekit, owner_room):
    """A member cannot close a session."""
    room, _client = owner_room
    session = make_session(room, ["alice"], ["bob"])
    member = UserFactory()
    UserResourceAccessFactory(resource=room, user=member, role="member")
    client = APIClient()
    client.force_login(member)

    response = client.post(url(room, f"{session.id!s}/close/"))

    assert response.status_code == 403
    livekit.room.delete_room.assert_not_awaited()


# Flag


def test_api_breakout_sessions_flag_off(livekit, owner_room, settings):
    """Flag off, every call answers 404 but close."""
    settings.MEET_BREAKOUT_ROOMS_ENABLED = False
    room, client = owner_room
    session = make_session(room, ["alice"], ["bob"])
    breakout_room = session.rooms.first()

    assert client.get(url(room)).status_code == 404
    assert client.post(url(room), payload(["a"], ["b"]), "json").status_code == 404
    assert client.get(url(room, "current-assignment/")).status_code == 404
    join = f"{session.id!s}/rooms/{breakout_room.id!s}/join/"
    assert client.post(url(room, join)).status_code == 404
    assert client.post(url(room, f"{session.id!s}/close/")).status_code == 200
    livekit.room.create_room.assert_not_awaited()


# Current assignment and join


def test_api_breakout_sessions_current_assignment_user(livekit):
    """A signed-in participant finds their room by their sub."""
    room = RoomFactory()
    user = UserFactory()
    session = make_session(room, ["alice"], [str(user.sub)])
    client = APIClient()
    client.force_login(user)

    response = client.get(url(room, "current-assignment/"))

    breakout_room = session.rooms.get(name="Room 2")
    assert response.status_code == 200
    assert response.json() == {
        "session_id": str(session.id),
        "room": {"id": str(breakout_room.id), "name": "Room 2"},
    }


def test_api_breakout_sessions_current_assignment_guest(livekit):
    """A guest finds their room by the identity their signed cookie gives."""
    room = RoomFactory()
    client, identity = guest_client(room)
    session = make_session(room, [identity], ["bob"])

    response = client.get(url(room, "current-assignment/"))

    assert response.status_code == 200
    assert response.json()["room"]["id"] == str(session.rooms.get(name="Room 1").id)
    assert APIClient().get(url(room, "current-assignment/")).status_code == 404


def test_api_breakout_sessions_current_assignment_closed(livekit):
    """A closed session assigns nobody."""
    room = RoomFactory()
    user = UserFactory()
    make_session(room, [str(user.sub)], ["bob"])
    models.BreakoutSession.objects.update(status=CLOSED)
    client = APIClient()
    client.force_login(user)

    assert client.get(url(room, "current-assignment/")).status_code == 404


def test_api_breakout_sessions_join(livekit):
    """The assigned participant gets a short member pass to that room only."""
    room = RoomFactory(configuration={"can_publish_sources": ["microphone"]})
    user = UserFactory()
    UserResourceAccessFactory(resource=room, user=user, role="owner")
    session = make_session(room, [str(user.sub)], ["bob"])
    own, other = session.rooms.all()
    client = APIClient()
    client.force_login(user)

    response = client.post(url(room, f"{session.id!s}/rooms/{own.id!s}/join/"))

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == settings.LIVEKIT_CONFIGURATION["url"]
    assert data["room"] == own.livekit_room_name
    claims = jwt.decode(
        data["token"],
        settings.LIVEKIT_CONFIGURATION["api_secret"],
        algorithms=["HS256"],
    )
    assert claims["sub"] == str(user.sub)
    assert claims["exp"] - claims["nbf"] == 60
    assert claims["video"]["room"] == own.livekit_room_name
    assert claims["video"].get("roomAdmin", False) is False
    assert claims["video"]["canPublishSources"] == ["microphone"]
    assert claims["attributes"]["room_role"] == "member"

    other_join = url(room, f"{session.id!s}/rooms/{other.id!s}/join/")
    assert client.post(other_join).status_code == 404


def test_api_breakout_sessions_join_guest(livekit):
    """A guest joins with the identity they hold in the meeting."""
    room = RoomFactory()
    client, identity = guest_client(room)
    session = make_session(room, [identity])
    breakout_room = session.rooms.get()

    response = client.post(
        url(room, f"{session.id!s}/rooms/{breakout_room.id!s}/join/")
    )

    assert response.status_code == 200
    claims = jwt.decode(response.json()["token"], options={"verify_signature": False})
    assert claims["sub"] == identity
