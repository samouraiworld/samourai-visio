# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,unused-import,line-too-long,unused-variable
"""Unit tests for BreakoutService."""

from datetime import timedelta
from unittest import mock

from django.utils import timezone

import pytest

from core.breakout.models import BreakoutAssignment, BreakoutRoom, BreakoutSession
from core.breakout.services import (
    GRACE_PERIOD_SECONDS,
    BreakoutService,
    BreakoutServiceError,
    InvalidSessionStateError,
    SessionAlreadyActiveError,
)
from core.breakout.tests.factories import (
    BreakoutAssignmentFactory,
    BreakoutRoomFactory,
    BreakoutSessionFactory,
)
from core.factories import RoomFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def service():
    return BreakoutService()


@mock.patch.object(BreakoutService, "_create_livekit_rooms")
def test_create_session_success(mock_create_lk, service):
    """Creating a session creates BreakoutSession and BreakoutRoom records."""
    room = RoomFactory()
    user = UserFactory()

    session = service.create_session(
        room=room,
        num_rooms=3,
        created_by=user,
        duration_seconds=600,
        room_names=["Discussion", "Brainstorming", "Wrapup"],
    )

    assert session.room == room
    assert session.created_by == user
    assert session.duration_seconds == 600
    assert session.status == BreakoutSession.Status.CONFIGURING

    rooms = list(session.breakout_rooms.order_by("order"))
    assert len(rooms) == 3
    assert rooms[0].name == "Discussion"
    assert rooms[1].name == "Brainstorming"
    assert rooms[2].name == "Wrapup"
    assert mock_create_lk.call_count == 1


@mock.patch.object(BreakoutService, "_create_livekit_rooms")
def test_create_session_already_active_raises(mock_create_lk, service):
    """Cannot create a new session if one is already configuring or active."""
    room = RoomFactory()
    user = UserFactory()
    BreakoutSessionFactory(room=room, status=BreakoutSession.Status.CONFIGURING)

    with pytest.raises(SessionAlreadyActiveError):
        service.create_session(room=room, num_rooms=2, created_by=user)


@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_activate_session_success(mock_update_meta, mock_send_data, service):
    """Activating a session transitions status to ACTIVE and updates metadata."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)
    br1 = BreakoutRoomFactory(session=session, order=0)
    br2 = BreakoutRoomFactory(session=session, order=1)
    BreakoutAssignmentFactory(breakout_room=br1, participant_identity="p1")

    activated = service.activate_session(session)

    assert activated.status == BreakoutSession.Status.ACTIVE
    assert activated.started_at is not None
    assert mock_update_meta.call_count == 1
    assert mock_send_data.call_count == 1


def test_activate_session_invalid_state_raises(service):
    """Cannot activate a session that is already active or closed."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)

    with pytest.raises(InvalidSessionStateError):
        service.activate_session(session)


@mock.patch.object(BreakoutService, "_delete_livekit_rooms")
@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_close_session_success(
    mock_update_meta, mock_send_data, mock_delete_lk, service
):
    """Closing a session sets CLOSED status, sends recall messages, and deletes LK rooms."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    BreakoutRoomFactory(session=session)
    BreakoutRoomFactory(session=session)

    closed = service.close_session(session)

    assert closed.status == BreakoutSession.Status.CLOSED
    assert closed.closed_at is not None
    assert mock_send_data.call_count == 2  # Once per breakout room
    assert mock_delete_lk.call_count == 1
    assert mock_update_meta.call_count == 1


def test_assign_participants_idempotent(service):
    """Assigning participants replaces existing assignments idempotently."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)
    br1 = BreakoutRoomFactory(session=session)
    br2 = BreakoutRoomFactory(session=session)

    # Initial assignment
    service.assign_participants(
        session,
        {
            str(br1.id): [{"identity": "p1", "name": "Alice"}],
            str(br2.id): [{"identity": "p2", "name": "Bob"}],
        },
    )
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 2
    )

    # Re-assignment: move Alice to br2, add Charlie
    service.assign_participants(
        session,
        {
            str(br1.id): [],
            str(br2.id): [
                {"identity": "p1", "name": "Alice"},
                {"identity": "p3", "name": "Charlie"},
            ],
        },
    )
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 2
    )
    assert br2.assignments.filter(participant_identity="p1").exists()


def test_assign_participants_duplicate_raises(service):
    """Assigning the same participant to multiple rooms raises an error."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)
    br1 = BreakoutRoomFactory(session=session)
    br2 = BreakoutRoomFactory(session=session)

    with pytest.raises(BreakoutServiceError):
        service.assign_participants(
            session,
            {
                str(br1.id): [{"identity": "p1", "name": "Alice"}],
                str(br2.id): [{"identity": "p1", "name": "Alice Duplicate"}],
            },
        )


def test_randomize_assignments(service):
    """Randomize distributes participants evenly across rooms."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)
    br1 = BreakoutRoomFactory(session=session, order=0)
    br2 = BreakoutRoomFactory(session=session, order=1)

    participants = [
        {"identity": "p1", "name": "Alice"},
        {"identity": "p2", "name": "Bob"},
        {"identity": "p3", "name": "Charlie"},
        {"identity": "p4", "name": "David"},
    ]

    assignments = service.randomize_assignments(session, participants)

    assert len(assignments[str(br1.id)]) == 2
    assert len(assignments[str(br2.id)]) == 2
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 4
    )


@mock.patch("core.utils.generate_token")
def test_generate_breakout_token_member_role(mock_gen_token, service):
    """Token generated for breakout rooms has role='member' (never admin)."""
    room = BreakoutRoomFactory()
    user = UserFactory()

    mock_gen_token.return_value = "fake.jwt.token"

    result = service.generate_breakout_token(
        breakout_room=room,
        user=user,
        username="Test User",
    )

    assert result["token"] == "fake.jwt.token"
    assert result["room"] == room.livekit_room_name
    mock_gen_token.assert_called_once()
    _, kwargs = mock_gen_token.call_args
    assert kwargs["role"] == "member"


@mock.patch.object(BreakoutService, "close_session")
def test_cleanup_stale_sessions(mock_close, service):
    """Stale active sessions exceeding duration + grace period are closed."""
    now = timezone.now()
    # Expired session: started 700s ago, duration was 300s
    expired_session = BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVE,
        started_at=now - timedelta(seconds=700),
        duration_seconds=300,
    )
    # Still active session: started 100s ago, duration is 300s
    BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVE,
        started_at=now - timedelta(seconds=100),
        duration_seconds=300,
    )

    closed_count = service.cleanup_stale_sessions()
    assert closed_count == 1
    mock_close.assert_called_once_with(expired_session)


@mock.patch.object(BreakoutService, "close_session")
def test_close_sessions_for_room(mock_close, service):
    """Closing sessions for a room closes all active and configuring sessions."""
    room = RoomFactory()
    s1 = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    BreakoutSessionFactory(room=room, status=BreakoutSession.Status.CLOSED)

    closed_count = service.close_sessions_for_room(room.id)
    assert closed_count == 1
    mock_close.assert_called_once_with(s1)


def test_assign_participants_transaction_rollback(service):
    """If an error occurs during bulk creation, prior assignments are preserved via atomic rollback."""
    session = BreakoutSessionFactory()
    room1 = BreakoutRoomFactory(session=session, order=0)
    BreakoutAssignmentFactory(
        breakout_room=room1,
        participant_identity="user-existing",
        participant_name="Existing User",
    )

    # Initial state: 1 assignment exists
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 1
    )

    # Simulate unexpected failure during bulk_create
    with mock.patch(
        "core.breakout.models.BreakoutAssignment.objects.bulk_create",
        side_effect=RuntimeError("Simulated DB error during bulk_create"),
    ):
        with pytest.raises(RuntimeError, match="Simulated DB error"):
            service.assign_participants(
                session,
                {str(room1.id): [{"identity": "user-new", "name": "New User"}]},
            )

    # Thanks to transaction.atomic(), rollback occurred: previous assignment is preserved
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 1
    )
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session)
        .first()
        .participant_identity
        == "user-existing"
    )


@mock.patch("core.breakout.services.utils.generate_token")
def test_generate_breakout_token_ttl_scoped(mock_gen_token, service):
    """Breakout room token TTL is scoped to session duration + grace period."""
    session = BreakoutSessionFactory(duration_seconds=600)
    b_room = BreakoutRoomFactory(session=session)
    mock_gen_token.return_value = "fake.scoped.jwt"

    service.generate_breakout_token(breakout_room=b_room)

    mock_gen_token.assert_called_once()
    _, kwargs = mock_gen_token.call_args
    assert kwargs["ttl"] == timedelta(seconds=900)  # 600 + 300


# ── Regression: Bug 2 — metadata must include full blob on reassignment ──────


@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_reassign_while_active_republishes_full_metadata(mock_meta, mock_send, service):
    """Reassigning during an active session must republish the whole breakout blob.

    _update_assignment_metadata used to push only {"breakout": {"assignments": ...}},
    which caused the top-level merge in RoomManagement.update_metadata to replace the
    entire "breakout" key, dropping status/session_id/rooms and making recall impossible.
    """
    session = BreakoutSessionFactory(
        status=BreakoutSession.Status.CONFIGURING, duration_seconds=600
    )
    br1 = BreakoutRoomFactory(session=session, order=0)
    br2 = BreakoutRoomFactory(session=session, order=1)

    service.activate_session(session)
    service.assign_participants(
        session, {str(br2.id): [{"identity": "p1", "name": "Alice"}]}
    )

    # The last call to update_metadata (from _update_assignment_metadata) must
    # carry the full breakout blob, not just the assignments dict.
    breakout = mock_meta.call_args.kwargs["metadata"]["breakout"]
    assert breakout["status"] == "active"
    assert breakout["session_id"] == str(session.id)
    assert [r["id"] for r in breakout["rooms"]] == [str(br1.id), str(br2.id)]


# ── Regression: Bug 3 — unknown room ID must not wipe existing assignments ────


def test_assign_unknown_room_id_raises_and_preserves_assignments(service):
    """An unknown breakout_room_id in the payload must raise and leave DB intact.

    assign_participants used to DELETE all assignments before resolving room IDs,
    so a stale payload with one bad ID wiped everything and returned 200.
    """
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)
    br = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(breakout_room=br, participant_identity="p1")

    with pytest.raises(BreakoutServiceError):
        service.assign_participants(
            session,
            {
                "00000000-0000-0000-0000-000000000000": [
                    {"identity": "p2", "name": "Bob"}
                ]
            },
        )

    # Original assignment must be intact
    assert (
        BreakoutAssignment.objects.filter(breakout_room__session=session).count() == 1
    )
    assert (
        BreakoutAssignment.objects.get(
            breakout_room__session=session
        ).participant_identity
        == "p1"
    )
