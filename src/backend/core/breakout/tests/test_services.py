# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,unused-import,line-too-long,unused-variable,too-many-lines,broad-exception-caught,use-implicit-booleaness-not-comparison,protected-access
"""Unit tests for BreakoutService."""

import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from types import SimpleNamespace
from unittest import mock

from django.db import connections
from django.utils import timezone

import pytest

from core import utils
from core.breakout.models import (
    BreakoutAssignment,
    BreakoutHelpRequest,
    BreakoutRoom,
    BreakoutSession,
)
from core.breakout.services import (
    BREAKOUT_TOKEN_TTL_SECONDS,
    EFFECT_LOCK_TIMEOUT_SECONDS,
    LIVEKIT_LIFECYCLE_TIMEOUT_SECONDS,
    LIVEKIT_RECONCILIATION_CONCURRENCY,
    LIVEKIT_RECONCILIATION_TIMEOUT_SECONDS,
    BreakoutService,
    BreakoutServiceError,
    BreakoutUpstreamError,
    InvalidSessionStateError,
    SessionAlreadyActiveError,
)
from core.breakout.tests.factories import (
    BreakoutAssignmentFactory,
    BreakoutRoomFactory,
    BreakoutSessionFactory,
)
from core.factories import RoomFactory, UserFactory
from core.services.room_management import RoomNotFoundException

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


def test_activate_session_rejects_duplicate_in_flight_effect(service):
    """A concurrent activation cannot duplicate an effect already in flight."""
    session = BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVATING,
        effect_error="",
    )

    with pytest.raises(
        InvalidSessionStateError, match="activation is already in progress"
    ):
        service.activate_session(session)


@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch(
    "core.services.room_management.RoomManagement.update_metadata",
    side_effect=RuntimeError("LiveKit unavailable"),
)
def test_activation_failure_remains_retryable(
    mock_update_meta, mock_send_data, service
):
    """A failed activation effect never advertises the session as completed."""
    session = BreakoutSessionFactory(
        status=BreakoutSession.Status.CONFIGURING,
        duration_seconds=300,
    )
    BreakoutRoomFactory(session=session)

    with pytest.raises(BreakoutUpstreamError):
        service.activate_session(session)

    session.refresh_from_db()
    assert session.status == BreakoutSession.Status.ACTIVATING
    assert session.started_at is not None
    assert session.ends_at == session.started_at + timedelta(seconds=300)
    assert session.effect_error == "LiveKit unavailable"


@mock.patch.object(
    BreakoutService,
    "_send_data_to_room",
    side_effect=RuntimeError("no connected recipients"),
)
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_activation_advisory_message_failure_does_not_block(
    mock_update_meta, mock_send_data, service
):
    """Authoritative metadata, not a best-effort data hint, completes activation."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)

    activated = service.activate_session(session)

    assert activated.status == BreakoutSession.Status.ACTIVE
    assert activated.effect_error == ""
    mock_update_meta.assert_called_once()
    mock_send_data.assert_called_once()


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


@mock.patch.object(
    BreakoutService,
    "_delete_livekit_rooms",
    side_effect=RuntimeError("LiveKit unavailable"),
)
@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_close_failure_remains_closing(
    mock_update_meta, mock_send_data, mock_delete_lk, service
):
    """A failed close is visible and retryable instead of falsely closed."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    BreakoutRoomFactory(session=session)

    with pytest.raises(BreakoutUpstreamError):
        service.close_session(session)

    session.refresh_from_db()
    assert session.status == BreakoutSession.Status.CLOSING
    assert session.closed_at is None
    assert session.effect_error == "LiveKit unavailable"


@mock.patch.object(BreakoutService, "_delete_livekit_rooms")
@mock.patch.object(
    BreakoutService,
    "_send_data_to_room",
    side_effect=RuntimeError("room already empty"),
)
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_close_advisory_recall_failure_does_not_block(
    mock_update_meta, mock_send_data, mock_delete_lk, service
):
    """Room deletion remains authoritative when no participant can receive recall."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    BreakoutRoomFactory(session=session)

    closed = service.close_session(session)

    assert closed.status == BreakoutSession.Status.CLOSED
    mock_update_meta.assert_called_once()
    mock_send_data.assert_called_once()
    mock_delete_lk.assert_called_once()


@mock.patch.object(BreakoutService, "_delete_livekit_rooms")
@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch(
    "core.services.room_management.RoomManagement.update_metadata",
    side_effect=RoomNotFoundException("parent room is already empty"),
)
def test_close_missing_parent_room_still_deletes_breakout_rooms(
    mock_update_meta, mock_send_data, mock_delete_lk, service
):
    """An already-absent parent room means its breakout metadata is absent too."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    BreakoutRoomFactory(session=session)

    closed = service.close_session(session)

    assert closed.status == BreakoutSession.Status.CLOSED
    mock_update_meta.assert_called_once()
    mock_send_data.assert_called_once()
    mock_delete_lk.assert_called_once()


@mock.patch.object(BreakoutService, "_delete_livekit_rooms")
@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch(
    "core.services.room_management.RoomManagement.update_metadata",
    side_effect=RuntimeError("metadata unavailable"),
)
def test_close_metadata_failure_preserves_rooms_for_retry(
    mock_update_meta, mock_send_data, mock_delete_lk, service
):
    """A failed authoritative metadata update must not delete rooms first."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    BreakoutRoomFactory(session=session)

    with pytest.raises(BreakoutUpstreamError):
        service.close_session(session)

    session.refresh_from_db()
    assert session.status == BreakoutSession.Status.CLOSING
    assert session.effect_error == "metadata unavailable"
    mock_send_data.assert_not_called()
    mock_delete_lk.assert_not_called()


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
        identity=str(user.sub),
        display_name="Test User",
    )

    assert result["token"] == "fake.jwt.token"
    assert result["room"] == room.livekit_room_name
    mock_gen_token.assert_called_once()
    _, kwargs = mock_gen_token.call_args
    assert kwargs["role"] == "member"


@pytest.mark.parametrize("sources", [[], ["camera"]])
@mock.patch("core.utils.generate_token")
def test_generate_breakout_token_preserves_parent_publication_policy(
    mock_gen_token, sources, service
):
    """Breakout grants must not widen an explicit main-room media policy."""
    room = RoomFactory(configuration={"can_publish_sources": sources})
    breakout_room = BreakoutRoomFactory(session__room=room)
    mock_gen_token.return_value = "fake.jwt.token"

    service.generate_breakout_token(
        breakout_room=breakout_room,
        identity="participant-1",
    )

    _, kwargs = mock_gen_token.call_args
    assert kwargs["sources"] == sources


@mock.patch.object(BreakoutService, "close_session")
def test_cleanup_stale_sessions(mock_close, service):
    """A timed active session is closed at its absolute deadline."""
    now = timezone.now()
    # Expired session: started 700s ago, duration was 300s
    expired_session = BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVE,
        started_at=now - timedelta(seconds=700),
        duration_seconds=300,
        ends_at=now - timedelta(seconds=400),
    )
    # Still active session: started 100s ago, duration is 300s
    BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVE,
        started_at=now - timedelta(seconds=100),
        duration_seconds=300,
        ends_at=now + timedelta(seconds=200),
    )

    closed_count = service.cleanup_stale_sessions()
    assert closed_count == 1
    mock_close.assert_called_once_with(expired_session)


@mock.patch.object(BreakoutService, "close_session")
def test_cleanup_ignores_untimed_sessions(mock_close, service):
    """Untimed sessions remain active until a manager explicitly closes them."""
    BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVE,
        started_at=timezone.now() - timedelta(days=1),
        duration_seconds=None,
        ends_at=None,
    )

    assert service.cleanup_stale_sessions() == 0
    mock_close.assert_not_called()


@mock.patch.object(BreakoutService, "activate_session")
def test_cleanup_retries_failed_activation(mock_activate, service):
    """The periodic reconciler recovers activation failures without a browser."""
    failed_session = BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVATING,
        effect_error="LiveKit unavailable",
    )

    assert service.cleanup_stale_sessions() == 1
    mock_activate.assert_called_once_with(failed_session)


@mock.patch.object(BreakoutService, "retry_session")
def test_cleanup_retries_active_assignment_reconciliation(mock_retry, service):
    """A failed active-session eviction is retried without closing the session."""
    failed_session = BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVE,
        ends_at=None,
        effect_error="LiveKit unavailable",
    )

    assert service.cleanup_stale_sessions() == 1

    mock_retry.assert_called_once_with(failed_session)


@mock.patch.object(BreakoutService, "retry_session")
@mock.patch.object(BreakoutService, "close_session")
def test_cleanup_closes_expired_active_session_before_retrying_effect(
    mock_close, mock_retry, service
):
    """The absolute deadline wins when an active session also has an effect error."""
    expired_session = BreakoutSessionFactory(
        status=BreakoutSession.Status.ACTIVE,
        ends_at=timezone.now() - timedelta(seconds=1),
        effect_error="LiveKit unavailable",
    )

    assert service.cleanup_stale_sessions() == 1

    mock_close.assert_called_once_with(expired_session)
    mock_retry.assert_not_called()


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


@mock.patch("core.breakout.services.timezone.now")
@mock.patch("core.breakout.services.utils.generate_token")
def test_generate_breakout_token_ttl_scoped(mock_gen_token, mock_now, service):
    """Breakout token TTL is short and capped by the absolute session end."""
    now = datetime(2030, 1, 1, tzinfo=UTC)
    mock_now.return_value = now
    session = BreakoutSessionFactory(
        duration_seconds=600,
        ends_at=now + timedelta(seconds=45),
    )
    b_room = BreakoutRoomFactory(session=session)
    mock_gen_token.return_value = "fake.scoped.jwt"

    service.generate_breakout_token(
        breakout_room=b_room,
        identity="participant-1",
        display_name="Participant 1",
    )

    mock_gen_token.assert_called_once()
    _, kwargs = mock_gen_token.call_args
    assert kwargs["ttl"] == timedelta(seconds=45)
    assert kwargs["can_publish_data"] is True


@mock.patch("core.breakout.services.utils.generate_token")
def test_generate_untimed_breakout_token_uses_short_ttl(mock_gen_token, service):
    """Untimed sessions still receive only short-lived join tokens."""
    breakout_room = BreakoutRoomFactory(session__duration_seconds=None)
    mock_gen_token.return_value = "fake.short.jwt"

    service.generate_breakout_token(
        breakout_room=breakout_room,
        identity="participant-1",
    )

    _, kwargs = mock_gen_token.call_args
    assert kwargs["ttl"] == timedelta(seconds=BREAKOUT_TOKEN_TTL_SECONDS)


# ── Regression: Bug 2 — metadata must include full blob on reassignment ──────


@mock.patch.object(BreakoutService, "_send_data_to_room")
@mock.patch.object(BreakoutService, "_reconcile_livekit_assignments")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_reassign_while_active_publishes_bounded_metadata(
    mock_meta, mock_reconcile, mock_send, service
):
    """Reassignment publishes a revision without exposing the full roster."""
    session = BreakoutSessionFactory(
        status=BreakoutSession.Status.CONFIGURING, duration_seconds=600
    )
    br1 = BreakoutRoomFactory(session=session, order=0)
    br2 = BreakoutRoomFactory(session=session, order=1)

    service.activate_session(session)
    service.assign_participants(
        session, {str(br2.id): [{"identity": "p1", "name": "Alice"}]}
    )

    breakout = mock_meta.call_args.kwargs["metadata"]["breakout"]
    assert breakout["status"] == "active"
    assert breakout["session_id"] == str(session.id)
    assert breakout["revision"] == 2
    assert "rooms" not in breakout
    assert "assignments" not in breakout
    mock_reconcile.assert_called_once()


@mock.patch.object(BreakoutService, "_reconcile_livekit_assignments")
@mock.patch(
    "core.services.room_management.RoomManagement.update_metadata",
    side_effect=RoomNotFoundException("parent room is already empty"),
)
def test_reassign_with_missing_parent_room_still_revokes_old_access(
    mock_meta, mock_reconcile, service
):
    """An empty parent room cannot prevent authoritative breakout eviction."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)

    service.assign_participants(
        session,
        {str(breakout_room.id): [{"identity": "p1", "name": "Alice"}]},
    )

    mock_reconcile.assert_called_once()
    session.refresh_from_db()
    assert session.effect_error == ""


@mock.patch.object(BreakoutService, "_reconcile_livekit_assignments")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_reassign_rebinds_open_help_to_current_room(mock_meta, mock_reconcile, service):
    """A manager help alert must follow the participant's current assignment."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE, revision=4)
    old_room = BreakoutRoomFactory(session=session)
    new_room = BreakoutRoomFactory(session=session)
    assignment = BreakoutAssignmentFactory(
        breakout_room=old_room,
        participant_identity="participant-1",
        participant_name="Alice",
    )
    help_request = BreakoutHelpRequest.objects.create(
        session=session,
        breakout_room=old_room,
        requester_identity=assignment.participant_identity,
        requester_name=assignment.participant_name,
        assignment_revision=session.revision,
    )

    service.assign_participants(
        session,
        {
            str(old_room.id): [],
            str(new_room.id): [{"identity": "participant-1", "name": "Alice Updated"}],
        },
        expected_revision=4,
    )

    help_request.refresh_from_db()
    assert help_request.breakout_room == new_room
    assert help_request.requester_name == "Alice Updated"
    assert help_request.assignment_revision == 5
    assert help_request.status == BreakoutHelpRequest.Status.OPEN


@mock.patch.object(BreakoutService, "_reconcile_livekit_assignments")
@mock.patch("core.services.room_management.RoomManagement.update_metadata")
def test_unassign_cancels_open_help_request(mock_meta, mock_reconcile, service):
    """An alert cannot keep pointing at a room after its requester is unassigned."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    old_room = BreakoutRoomFactory(session=session)
    assignment = BreakoutAssignmentFactory(
        breakout_room=old_room,
        participant_identity="participant-1",
    )
    help_request = BreakoutHelpRequest.objects.create(
        session=session,
        breakout_room=old_room,
        requester_identity=assignment.participant_identity,
    )

    service.assign_participants(session, {str(old_room.id): []})

    help_request.refresh_from_db()
    assert help_request.status == BreakoutHelpRequest.Status.CANCELLED
    assert help_request.cancelled_at is not None


@mock.patch.object(BreakoutService, "_remove_participant")
def test_webhook_enforcement_removes_stale_assignment_token(mock_remove, service):
    """A participant rejoining a previous room with a cached token is evicted."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    old_room = BreakoutRoomFactory(session=session)
    new_room = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(
        breakout_room=new_room,
        participant_identity="participant-1",
    )

    assert (
        service.enforce_breakout_participant_access(
            old_room.livekit_room_name, "participant-1"
        )
        is False
    )
    mock_remove.assert_called_once_with(old_room.livekit_room_name, "participant-1")


@mock.patch.object(BreakoutService, "_remove_participant")
def test_webhook_enforcement_allows_current_assignment(mock_remove, service):
    """The reconnect guard keeps participants in their authoritative room."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(
        breakout_room=breakout_room,
        participant_identity="participant-1",
    )

    assert (
        service.enforce_breakout_participant_access(
            breakout_room.livekit_room_name, "participant-1"
        )
        is True
    )
    mock_remove.assert_not_called()


@mock.patch.object(BreakoutService, "_remove_participant")
def test_webhook_enforcement_allows_current_room_manager(mock_remove, service):
    """Authorized managers can still visit rooms without participant assignments."""
    manager = UserFactory()
    room = RoomFactory(users=[(manager, "owner")])
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)

    assert (
        service.enforce_breakout_participant_access(
            breakout_room.livekit_room_name, str(manager.sub)
        )
        is True
    )
    mock_remove.assert_not_called()


def test_assignment_revision_conflict_preserves_state(service):
    """A stale manager write cannot overwrite a newer assignment revision."""
    session = BreakoutSessionFactory(revision=3)
    breakout_room = BreakoutRoomFactory(session=session)

    with pytest.raises(InvalidSessionStateError):
        service.assign_participants(
            session,
            {
                str(breakout_room.id): [
                    {"identity": "participant-1", "name": "Participant"}
                ]
            },
            expected_revision=2,
        )

    assert session.assignments.count() == 0


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


@pytest.mark.django_db(transaction=True)
def test_close_waits_for_activation_livekit_effect(service):
    """A close cannot overtake activation and leave active metadata behind."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)
    BreakoutRoomFactory(session=session)
    activation_effect_started = Event()
    allow_activation_effect = Event()
    close_started = Event()
    close_finished = Event()
    effect_order = []
    errors = []

    def update_metadata(*, metadata=None, remove_keys=None, **kwargs):
        if metadata:
            effect_order.append("activate")
            activation_effect_started.set()
            assert allow_activation_effect.wait(5)
        if remove_keys:
            effect_order.append("close")

    def run(operation, finished=None):
        connections.close_all()
        try:
            operation()
        except Exception as error:  # noqa: BLE001
            errors.append(error)
        finally:
            connections.close_all()
            if finished:
                finished.set()

    with (
        mock.patch(
            "core.services.room_management.RoomManagement.update_metadata",
            side_effect=update_metadata,
        ),
        mock.patch.object(BreakoutService, "_send_data_to_room"),
        mock.patch.object(BreakoutService, "_delete_livekit_rooms"),
    ):
        activate_thread = Thread(
            target=lambda: run(lambda: service.activate_session(session))
        )
        activate_thread.start()
        assert activation_effect_started.wait(5)

        def close():
            close_started.set()
            service.close_session(session)

        close_thread = Thread(target=lambda: run(close, close_finished))
        close_thread.start()
        assert close_started.wait(5)
        assert not close_finished.wait(0.2)

        allow_activation_effect.set()
        activate_thread.join(5)
        close_thread.join(5)

    session.refresh_from_db()
    assert errors == []
    assert effect_order == ["activate", "close"]
    assert session.status == BreakoutSession.Status.CLOSED


@pytest.mark.django_db(transaction=True)
def test_close_waits_for_assignment_reconciliation(service):
    """A delayed assignment cannot republish active metadata after close."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)
    reconciliation_started = Event()
    allow_reconciliation = Event()
    close_started = Event()
    close_finished = Event()
    metadata_order = []
    errors = []

    def reconcile(_session):
        reconciliation_started.set()
        assert allow_reconciliation.wait(5)

    def update_metadata(*, metadata=None, remove_keys=None, **kwargs):
        if metadata:
            metadata_order.append("assign")
        if remove_keys:
            metadata_order.append("close")

    def run(operation, finished=None):
        connections.close_all()
        try:
            operation()
        except Exception as error:  # noqa: BLE001
            errors.append(error)
        finally:
            connections.close_all()
            if finished:
                finished.set()

    with (
        mock.patch.object(
            BreakoutService, "_reconcile_livekit_assignments", side_effect=reconcile
        ),
        mock.patch(
            "core.services.room_management.RoomManagement.update_metadata",
            side_effect=update_metadata,
        ),
        mock.patch.object(BreakoutService, "_send_data_to_room"),
        mock.patch.object(BreakoutService, "_delete_livekit_rooms"),
    ):
        assign_thread = Thread(
            target=lambda: run(
                lambda: service.assign_participants(
                    session,
                    {
                        str(breakout_room.id): [
                            {"identity": "participant-1", "name": "Alice"}
                        ]
                    },
                )
            )
        )
        assign_thread.start()
        assert reconciliation_started.wait(5)

        def close():
            close_started.set()
            service.close_session(session)

        close_thread = Thread(target=lambda: run(close, close_finished))
        close_thread.start()
        assert close_started.wait(5)
        assert not close_finished.wait(0.2)

        allow_reconciliation.set()
        assign_thread.join(5)
        close_thread.join(5)

    session.refresh_from_db()
    assert errors == []
    assert metadata_order == ["assign", "close"]
    assert session.status == BreakoutSession.Status.CLOSED


@pytest.mark.django_db(transaction=True)
def test_help_request_waits_for_reassignment_and_uses_current_room(service):
    """A concurrent help request cannot retain the pre-reassignment room."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    old_room = BreakoutRoomFactory(session=session)
    new_room = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(
        breakout_room=old_room,
        participant_identity="participant-1",
        participant_name="Alice",
    )
    bulk_create_started = Event()
    allow_bulk_create = Event()
    help_started = Event()
    help_finished = Event()
    errors = []
    result = []
    original_bulk_create = BreakoutAssignment.objects.bulk_create

    def blocking_bulk_create(objects, *args, **kwargs):
        created = original_bulk_create(objects, *args, **kwargs)
        bulk_create_started.set()
        assert allow_bulk_create.wait(5)
        return created

    def run(operation, finished=None):
        connections.close_all()
        try:
            operation()
        except Exception as error:  # noqa: BLE001
            errors.append(error)
        finally:
            connections.close_all()
            if finished:
                finished.set()

    with (
        mock.patch.object(
            BreakoutAssignment.objects,
            "bulk_create",
            side_effect=blocking_bulk_create,
        ),
        mock.patch.object(BreakoutService, "_reconcile_livekit_assignments"),
        mock.patch("core.services.room_management.RoomManagement.update_metadata"),
        mock.patch.object(BreakoutService, "_send_data_to_room"),
    ):
        assign_thread = Thread(
            target=lambda: run(
                lambda: service.assign_participants(
                    session,
                    {
                        str(old_room.id): [],
                        str(new_room.id): [
                            {"identity": "participant-1", "name": "Alice"}
                        ],
                    },
                )
            )
        )
        assign_thread.start()
        assert bulk_create_started.wait(5)

        def request_help():
            help_started.set()
            result.append(service.create_help_request(session, "participant-1"))

        help_thread = Thread(target=lambda: run(request_help, help_finished))
        help_thread.start()
        assert help_started.wait(5)
        assert not help_finished.wait(0.2)

        allow_bulk_create.set()
        assign_thread.join(5)
        help_thread.join(5)

    assert errors == []
    help_request, created = result[0]
    assert created is True
    assert help_request.breakout_room_id == new_room.id


@pytest.mark.django_db(transaction=True)
def test_help_request_is_rejected_after_close_begins(service):
    """A close committed before help creation prevents a new open alert."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(
        breakout_room=breakout_room,
        participant_identity="participant-1",
    )
    close_effect_started = Event()
    allow_close_effect = Event()
    errors = []

    def update_metadata(*, remove_keys=None, **kwargs):
        if remove_keys:
            close_effect_started.set()
            assert allow_close_effect.wait(5)

    def close():
        connections.close_all()
        try:
            service.close_session(session)
        except Exception as error:  # noqa: BLE001
            errors.append(error)
        finally:
            connections.close_all()

    with (
        mock.patch(
            "core.services.room_management.RoomManagement.update_metadata",
            side_effect=update_metadata,
        ),
        mock.patch.object(BreakoutService, "_send_data_to_room"),
        mock.patch.object(BreakoutService, "_delete_livekit_rooms"),
    ):
        close_thread = Thread(target=close)
        close_thread.start()
        assert close_effect_started.wait(5)

        with pytest.raises(InvalidSessionStateError, match="no longer active"):
            service.create_help_request(session, "participant-1")

        allow_close_effect.set()
        close_thread.join(5)

    assert errors == []
    assert not BreakoutHelpRequest.objects.filter(session=session).exists()


def test_effect_lock_outlives_bounded_livekit_call_budget():
    """The effect mutex cannot expire before all bounded room calls finish."""
    worst_case_seconds = (
        2 * LIVEKIT_LIFECYCLE_TIMEOUT_SECONDS
        + LIVEKIT_RECONCILIATION_TIMEOUT_SECONDS
        + utils.LIVEKIT_HTTP_TIMEOUT_SECONDS
    )
    assert EFFECT_LOCK_TIMEOUT_SECONDS > worst_case_seconds


def test_broadcast_attempts_every_destination_before_reporting_failure(service):
    """One failed destination cannot prevent attempts to the other rooms."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    breakout_rooms = [
        BreakoutRoomFactory(session=session, order=order) for order in range(2)
    ]
    attempted = []

    def send(room_name, _payload):
        attempted.append(room_name)
        if room_name == breakout_rooms[0].livekit_room_name:
            raise RuntimeError("destination unavailable")

    with mock.patch.object(BreakoutService, "_send_data_to_room", side_effect=send):
        with pytest.raises(BreakoutUpstreamError, match="could not be delivered"):
            service.broadcast_message(session, "Important message")

    assert set(attempted) == {
        breakout_rooms[0].livekit_room_name,
        breakout_rooms[1].livekit_room_name,
        str(session.room_id),
    }


def test_reconciliation_limits_concurrent_livekit_requests():
    """Large sessions cannot exceed the configured LiveKit request fan-out."""

    class RoomService:
        def __init__(self):
            self.active = 0
            self.maximum = 0

        async def list_participants(self, _request):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return SimpleNamespace(participants=[])

    room_service = RoomService()
    client = SimpleNamespace(room=room_service, aclose=mock.AsyncMock())

    with mock.patch(
        "core.breakout.services.utils.create_livekit_client", return_value=client
    ):
        BreakoutService._reconcile_livekit_participants(
            {}, set(), [f"room-{index}" for index in range(25)]
        )

    assert 1 < room_service.maximum <= LIVEKIT_RECONCILIATION_CONCURRENCY
    client.aclose.assert_awaited_once()


def test_reconciliation_timeout_cancels_and_closes_livekit_client():
    """A stalled reconciliation respects its aggregate timeout and closes I/O."""

    async def never_returns(_request):
        await asyncio.Event().wait()

    client = SimpleNamespace(
        room=SimpleNamespace(list_participants=never_returns),
        aclose=mock.AsyncMock(),
    )

    with (
        mock.patch(
            "core.breakout.services.utils.create_livekit_client",
            return_value=client,
        ),
        mock.patch(
            "core.breakout.services.LIVEKIT_RECONCILIATION_TIMEOUT_SECONDS",
            0.01,
        ),
        pytest.raises(TimeoutError),
    ):
        BreakoutService._reconcile_livekit_participants({}, set(), ["room-1"])

    client.aclose.assert_awaited_once()
