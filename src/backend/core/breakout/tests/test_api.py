# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,unused-import,line-too-long,unused-variable
"""API integration tests for BreakoutSessionViewSet."""

from unittest import mock

import pytest
from rest_framework.test import APIClient

from core.breakout.models import BreakoutAssignment, BreakoutRoom, BreakoutSession
from core.breakout.tests.factories import (
    BreakoutAssignmentFactory,
    BreakoutRoomFactory,
    BreakoutSessionFactory,
)
from core.factories import RoomFactory, UserFactory
from core.models import RoleChoices

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enable_feature_flag(settings):
    settings.MEET_BREAKOUT_ROOMS_ENABLED = True
    settings.SECRET_KEY = "test-secret-key-for-testing-purposes-only"


def test_feature_flag_disabled_returns_404(settings):
    """When feature flag is disabled, all breakout endpoints return 404."""
    settings.MEET_BREAKOUT_ROOMS_ENABLED = False
    room = RoomFactory()
    user = UserFactory()
    room.accesses.create(user=user, role=RoleChoices.ADMIN)

    client = APIClient()
    client.force_login(user)

    response = client.get(f"/api/v1.0/rooms/{room.id}/breakout-sessions/")
    assert response.status_code == 404


def test_create_breakout_session_forbidden_for_non_admin():
    """Regular participants cannot create breakout sessions."""
    room = RoomFactory()
    user = UserFactory()
    room.accesses.create(user=user, role=RoleChoices.MEMBER)

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/",
        {"num_rooms": 2},
        format="json",
    )
    assert response.status_code == 403


@mock.patch("core.breakout.services.BreakoutService._create_livekit_rooms")
def test_create_breakout_session_admin_success(mock_lk_create):
    """Room administrator can successfully create a breakout session."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)

    client = APIClient()
    client.force_login(admin)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/",
        {
            "num_rooms": 3,
            "duration_seconds": 600,
            "room_names": ["Room A", "Room B", "Room C"],
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "configuring"
    assert data["duration_seconds"] == 600
    assert len(data["breakout_rooms"]) == 3
    assert data["breakout_rooms"][0]["name"] == "Room A"


def test_create_breakout_session_conflict():
    """Attempting to create a second session when one is already active returns 409."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    BreakoutSessionFactory(room=room, status=BreakoutSession.Status.CONFIGURING)

    client = APIClient()
    client.force_login(admin)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/",
        {"num_rooms": 2},
        format="json",
    )
    assert response.status_code == 409


def test_list_breakout_sessions():
    """List returns active and configuring sessions for the room."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)

    session = BreakoutSessionFactory(
        room=room, status=BreakoutSession.Status.CONFIGURING
    )
    BreakoutRoomFactory(session=session)

    client = APIClient()
    client.force_login(admin)

    response = client.get(f"/api/v1.0/rooms/{room.id}/breakout-sessions/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(session.id)


@mock.patch("core.breakout.services.BreakoutService._send_data_to_room")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_partial_update_activate(mock_meta, mock_send):
    """PATCH with status='active' activates the session."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(
        room=room, status=BreakoutSession.Status.CONFIGURING
    )

    client = APIClient()
    client.force_login(admin)

    response = client.patch(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/",
        {"status": "active"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    session.refresh_from_db()
    assert session.is_active is True


def test_bulk_assignments():
    """PUT assignments updates participant room allocations."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(
        room=room, status=BreakoutSession.Status.CONFIGURING
    )
    br = BreakoutRoomFactory(session=session)

    client = APIClient()
    client.force_login(admin)

    response = client.put(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/assignments/",
        {
            "assignments": {
                str(br.id): [{"identity": "user-sub-1", "name": "Participant 1"}]
            }
        },
        format="json",
    )

    assert response.status_code == 200
    assert BreakoutAssignment.objects.filter(
        breakout_room=br, participant_identity="user-sub-1"
    ).exists()


def test_randomize_endpoint():
    """POST randomize distributes participants evenly."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(
        room=room, status=BreakoutSession.Status.CONFIGURING
    )
    BreakoutRoomFactory(session=session)
    BreakoutRoomFactory(session=session)

    client = APIClient()
    client.force_login(admin)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/randomize/",
        {
            "participants": [
                {"identity": "p1", "name": "User 1"},
                {"identity": "p2", "name": "User 2"},
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 2
    )


@mock.patch("core.utils.generate_token")
def test_join_breakout_room_success(mock_token):
    """Assigned participant receives a LiveKit connection payload."""
    room = RoomFactory()
    user = UserFactory(sub="auth_sub_123")
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    br = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(breakout_room=br, participant_identity="auth_sub_123")

    mock_token.return_value = "jwt-test-token"

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/rooms/{br.id}/join/",
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert "livekit" in data
    assert data["livekit"]["token"] == "jwt-test-token"
    assert data["livekit"]["room"] == br.livekit_room_name


def test_join_breakout_room_unassigned_forbidden():
    """Unassigned participant gets 403 Forbidden."""
    room = RoomFactory()
    user = UserFactory(sub="unassigned_user")
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    br = BreakoutRoomFactory(session=session)

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/rooms/{br.id}/join/",
        format="json",
    )

    assert response.status_code == 403


@mock.patch("core.breakout.services.BreakoutService._send_data_to_room")
def test_broadcast_message_success(mock_send):
    """Administrator can broadcast announcement message to all breakout rooms."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    BreakoutRoomFactory(session=session)
    BreakoutRoomFactory(session=session)

    client = APIClient()
    client.force_login(admin)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/broadcast/",
        {"message": "Hello everyone!"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "broadcast_sent"
    assert response.json()["recipient_rooms"] == 2
    assert mock_send.call_count == 3  # 2 breakout rooms + 1 main room


def test_broadcast_message_forbidden_non_admin():
    """Non-admin participant cannot broadcast messages."""
    room = RoomFactory()
    user = UserFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)

    client = APIClient()
    client.force_login(user)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/broadcast/",
        {"message": "Spam message"},
        format="json",
    )

    assert response.status_code == 403


@mock.patch("core.breakout.services.BreakoutService._create_livekit_rooms")
def test_create_session_with_extended_duration(mock_create_lk):
    """Session can be created with up to 8 hours duration (28800s)."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)

    client = APIClient()
    client.force_login(admin)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/",
        {"num_rooms": 3, "duration_seconds": 14400},  # 4 hours
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["duration_seconds"] == 14400


def test_request_help_success():
    """Participants can request help from the host."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    b_room = BreakoutRoomFactory(session=session)
    BreakoutAssignment.objects.create(
        breakout_room=b_room,
        participant_identity="alice-123",
        participant_name="Alice",
    )

    client = APIClient()
    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/request-help/"
    with mock.patch("core.breakout.services.utils.notify_participants"):
        resp = client.post(
            url,
            {
                "breakout_room_id": str(b_room.id),
                "participant_id": "alice-123",
                "participant_name": "Alice",
            },
            format="json",
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "help_requested"


def test_request_help_rate_limiting_returns_429():
    """Participants attempting to spam help requests are rate-limited to 1 per 15s."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    b_room = BreakoutRoomFactory(session=session)
    BreakoutAssignment.objects.create(
        breakout_room=b_room,
        participant_identity="bob-123",
        participant_name="Bob",
    )

    client = APIClient()
    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/request-help/"
    payload = {
        "breakout_room_id": str(b_room.id),
        "participant_name": "Bob",
        "participant_id": "bob-123",
    }
    with mock.patch("core.breakout.services.utils.notify_participants"):
        # First request succeeds
        resp1 = client.post(url, payload, format="json")
        assert resp1.status_code == 200

        # Immediate follow-up request gets 429
        resp2 = client.post(url, payload, format="json")
        assert resp2.status_code == 429
        assert resp2.json()["detail"] == "Please wait before requesting help again."


def test_join_breakout_room_inactive_session_returns_400():
    """Attempting to join a breakout room when session is configuring returns 400."""
    room = RoomFactory()
    session = BreakoutSessionFactory(
        room=room, status=BreakoutSession.Status.CONFIGURING
    )
    b_room = BreakoutRoomFactory(session=session)

    client = APIClient()
    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/rooms/{b_room.id}/join/"
    resp = client.post(url, {"username": "GuestUser"}, format="json")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Breakout session is not active."


def test_can_manage_rejects_unauthenticated_even_in_debug(settings):
    """Even when DEBUG=True, unauthenticated users cannot manage breakout sessions."""
    settings.DEBUG = True
    room = RoomFactory()

    client = APIClient()
    resp = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/",
        {"num_rooms": 2},
        format="json",
    )
    assert resp.status_code == 403


def test_list_breakout_sessions_unauthenticated_returns_403():
    """Unauthenticated users cannot list breakout sessions."""
    room = RoomFactory()
    BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)

    client = APIClient()
    response = client.get(f"/api/v1.0/rooms/{room.id}/breakout-sessions/")
    assert response.status_code == 403


def test_join_breakout_room_anonymous_with_matching_identity():
    """Anonymous participant with valid assigned identity can join their assigned breakout room."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    b_room = BreakoutRoomFactory(session=session)
    anon_identity = "livekit-anon-uuid-456"
    BreakoutAssignment.objects.create(
        breakout_room=b_room,
        participant_identity=anon_identity,
        participant_name="Anonymous Guest",
    )

    client = APIClient()
    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/rooms/{b_room.id}/join/"
    with mock.patch("core.utils.generate_token") as mock_token:
        mock_token.return_value = "mocked-anon-jwt-token"

        resp = client.post(
            url,
            {"username": "Guest", "participant_id": anon_identity},
            format="json",
        )
    assert resp.status_code == 200
    assert resp.json()["livekit"]["token"] == "mocked-anon-jwt-token"


def test_join_breakout_room_anonymous_unassigned_returns_403():
    """Anonymous participant attempting to join a room they are not assigned to gets 403."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    b_room = BreakoutRoomFactory(session=session)

    client = APIClient()
    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/rooms/{b_room.id}/join/"
    resp = client.post(
        url,
        {"username": "Guest", "participant_id": "random-unassigned-id"},
        format="json",
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "You are not assigned to this breakout room."


# ── Regression: W2-1 — list returns [] for authenticated members ──────────────


def test_list_breakout_sessions_returns_empty_for_member():
    """Authenticated room member gets [] instead of 403 on the list endpoint."""
    room = RoomFactory()
    member = UserFactory()
    room.accesses.create(user=member, role=RoleChoices.MEMBER)
    # Create an active session as admin
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)

    client = APIClient()
    client.force_login(member)

    response = client.get(f"/api/v1.0/rooms/{room.id}/breakout-sessions/")
    assert response.status_code == 200
    # Member sees empty list, not the session details
    assert response.json() == []


# ── Regression: W2-2 — BulkAssign bounds prevent DoS ────────────────────────


def test_assignments_exceeding_room_limit_returns_400():
    """Sending >10 rooms in assignments payload returns 400."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(room=room)
    br = BreakoutRoomFactory(session=session)

    client = APIClient()
    client.force_login(admin)

    # Build a payload with 11 rooms (limit is 10)
    oversized = {str(br.id): []} | {
        f"00000000-0000-0000-0000-{str(i).zfill(12)}": [] for i in range(11)
    }
    response = client.put(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/assignments/",
        {"assignments": oversized},
        format="json",
    )
    assert response.status_code == 400


# ── Regression: Bug 3 / W2-5 — unknown room ID → 400, DB preserved ──────────


def test_assignments_unknown_room_id_returns_400_and_preserves_db():
    """Unknown room ID in assignments → 400 and existing assignments are intact."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(
        room=room, status=BreakoutSession.Status.CONFIGURING
    )
    br = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(breakout_room=br, participant_identity="original-p1")

    client = APIClient()
    client.force_login(admin)

    response = client.put(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/assignments/",
        {
            "assignments": {
                "00000000-0000-0000-0000-000000000000": [
                    {"identity": "p2", "name": "Ghost"}
                ]
            }
        },
        format="json",
    )
    assert response.status_code == 400

    # Original assignment must be intact
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 1
    )
    assert (
        BreakoutAssignment.objects.get(
            breakout_room__session=session
        ).participant_identity
        == "original-p1"
    )
