# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,unused-import,line-too-long,unused-variable
"""API integration tests for BreakoutSessionViewSet."""

from threading import Event, Thread
from time import monotonic, sleep
from unittest import mock

from django.db import connection, connections, transaction

import pytest
from rest_framework.test import APIClient

from core.breakout.models import (
    BreakoutAssignment,
    BreakoutHelpRequest,
    BreakoutRoom,
    BreakoutSession,
)
from core.breakout.services import BreakoutService
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
    settings.CELERY_ENABLED = True
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


def test_feature_flag_requires_celery_scheduler(settings):
    """Breakout APIs stay disabled without authoritative timed cleanup."""
    settings.MEET_BREAKOUT_ROOMS_ENABLED = True
    settings.CELERY_ENABLED = False
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    client = APIClient()
    client.force_login(admin)

    response = client.get(f"/api/v1.0/rooms/{room.id}/breakout-sessions/")
    config_response = client.get("/api/v1.0/config/")

    assert response.status_code == 404
    assert config_response.status_code == 200
    assert config_response.json()["breakout_rooms"]["is_enabled"] is False


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


@mock.patch(
    "core.services.room_management.RoomManagement.update_metadata",
    side_effect=RuntimeError("LiveKit unavailable"),
)
def test_activation_effect_failure_returns_503(mock_meta):
    """The API exposes a retryable activation failure without reporting active."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(room=room)
    client = APIClient()
    client.force_login(admin)

    response = client.patch(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/",
        {"status": "active"},
        format="json",
    )

    assert response.status_code == 503
    session.refresh_from_db()
    assert session.status == BreakoutSession.Status.ACTIVATING


@mock.patch("core.breakout.viewsets.BreakoutService.retry_session")
def test_retry_effect_is_available_to_room_manager(mock_retry):
    """A room manager can invoke the explicit effect-recovery endpoint."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(
        room=room,
        status=BreakoutSession.Status.ACTIVATING,
        effect_error="LiveKit unavailable",
    )
    mock_retry.return_value = session
    client = APIClient()
    client.force_login(admin)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/retry/",
        format="json",
    )

    assert response.status_code == 200
    mock_retry.assert_called_once_with(session)


@mock.patch("core.breakout.viewsets.BreakoutService.retry_session")
def test_retry_effect_is_forbidden_to_room_member(mock_retry):
    """An ordinary room member cannot invoke lifecycle reconciliation."""
    room = RoomFactory()
    member = UserFactory()
    room.accesses.create(user=member, role=RoleChoices.MEMBER)
    session = BreakoutSessionFactory(
        room=room,
        status=BreakoutSession.Status.ACTIVATING,
        effect_error="LiveKit unavailable",
    )
    client = APIClient()
    client.force_login(member)

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/retry/",
        format="json",
    )

    assert response.status_code == 403
    mock_retry.assert_not_called()


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
            "revision": session.revision,
            "assignments": {
                str(br.id): [{"identity": "user-sub-1", "name": "Participant 1"}]
            },
        },
        format="json",
    )

    assert response.status_code == 200
    assert BreakoutAssignment.objects.filter(
        breakout_room=br, participant_identity="user-sub-1"
    ).exists()


def test_bulk_assignments_rejects_stale_revision():
    """Concurrent moderator edits return conflict instead of losing updates."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(room=room, revision=2)
    breakout_room = BreakoutRoomFactory(session=session)
    client = APIClient()
    client.force_login(admin)

    response = client.put(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/assignments/",
        {
            "revision": 1,
            "assignments": {str(breakout_room.id): []},
        },
        format="json",
    )

    assert response.status_code == 409


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
            "revision": session.revision,
            "participants": [
                {"identity": "p1", "name": "User 1"},
                {"identity": "p2", "name": "User 2"},
            ],
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
    """A signed participant can create a durable help request."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    b_room = BreakoutRoomFactory(session=session)
    client = APIClient()
    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/request-help/"
    with mock.patch("core.breakout.services.utils.notify_participants"):
        entry = client.post(
            f"/api/v1.0/rooms/{room.id}/request-entry/",
            {"username": "Alice"},
            format="json",
        )
        BreakoutAssignment.objects.create(
            breakout_room=b_room,
            participant_identity=entry.json()["id"],
            participant_name="Alice",
        )
        resp = client.post(url, {}, format="json")
    assert resp.status_code == 201
    assert resp.json()["status"] == "open"
    assert resp.json()["requester_name"] == "Alice"


def test_request_help_rate_limiting_returns_429():
    """Creating a new help request during the cooldown is rejected."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    b_room = BreakoutRoomFactory(session=session)
    client = APIClient()
    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/request-help/"
    with mock.patch("core.breakout.services.utils.notify_participants"):
        entry = client.post(
            f"/api/v1.0/rooms/{room.id}/request-entry/",
            {"username": "Bob"},
            format="json",
        )
        BreakoutAssignment.objects.create(
            breakout_room=b_room,
            participant_identity=entry.json()["id"],
            participant_name="Bob",
        )
        assert client.post(url, {}, format="json").status_code == 201
        assert client.post(url, {}, format="json").status_code == 200
        cancel_url = (
            f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/cancel-help/"
        )
        assert client.post(cancel_url, {}, format="json").status_code == 200
        resp2 = client.post(url, {}, format="json")
        assert resp2.status_code == 429
        assert resp2.json()["detail"] == "Please wait before requesting help again."


def test_participant_can_cancel_own_help_request():
    """The signed participant can cancel, but cannot select another identity."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)
    client = APIClient()
    with mock.patch("core.services.lobby.utils.notify_participants"):
        entry = client.post(
            f"/api/v1.0/rooms/{room.id}/request-entry/",
            {"username": "Alice"},
            format="json",
        )
    assignment = BreakoutAssignment.objects.create(
        breakout_room=breakout_room,
        participant_identity=entry.json()["id"],
        participant_name="Alice",
    )
    help_request = BreakoutHelpRequest.objects.create(
        session=session,
        breakout_room=assignment.breakout_room,
        requester_identity=assignment.participant_identity,
        requester_name=assignment.participant_name,
    )

    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/cancel-help/",
        {"requester_identity": "someone-else"},
        format="json",
    )

    assert response.status_code == 200
    help_request.refresh_from_db()
    assert help_request.status == BreakoutHelpRequest.Status.CANCELLED
    assert help_request.cancelled_at is not None


@pytest.mark.django_db(transaction=True)
def test_cancel_cannot_overwrite_concurrent_acknowledgement():
    """A waiting cancellation rechecks terminal state after the host commits."""
    participant = UserFactory()
    session = BreakoutSessionFactory(status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)
    help_request = BreakoutHelpRequest.objects.create(
        session=session, breakout_room=breakout_room, requester_identity=participant.sub
    )
    ready = Event()
    result = {}

    def cancel():
        try:
            client = APIClient()
            client.force_authenticate(user=participant)
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                result["pid"] = cursor.fetchone()[0]
            ready.set()
            result["response"] = client.post(
                f"/api/v1.0/rooms/{session.room_id}/breakout-sessions/{session.id}/cancel-help/"
            )
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            result["error"] = error
        finally:
            connections.close_all()

    worker = Thread(target=cancel)
    with transaction.atomic():
        BreakoutSession.objects.select_for_update().get(pk=session.pk)
        help_request.status = BreakoutHelpRequest.Status.ACKNOWLEDGED
        help_request.save(update_fields=["status"])
        worker.start()
        assert ready.wait(5)
        deadline = monotonic() + 5
        blocked = False
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                    [result["pid"]],
                )
                blocked = cursor.fetchone() == ("Lock",)
            if blocked:
                break
            sleep(0.01)
        assert blocked, "Cancellation must overlap the uncommitted acknowledgement"
    worker.join(5)
    assert not worker.is_alive()
    assert "error" not in result
    assert result["response"].status_code == 404
    help_request.refresh_from_db()
    assert help_request.status == BreakoutHelpRequest.Status.ACKNOWLEDGED


def test_manager_can_list_and_acknowledge_help_from_another_breakout():
    """Help remains visible and actionable regardless of the manager's media room."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    breakout_room = BreakoutRoomFactory(session=session)
    help_request = BreakoutHelpRequest.objects.create(
        session=session,
        breakout_room=breakout_room,
        requester_identity="participant-a",
        requester_name="Alice",
    )
    client = APIClient()
    client.force_login(admin)

    list_response = client.get(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/help-requests/"
    )
    ack_response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/acknowledge-help/",
        {
            "help_request_id": str(help_request.id),
            "expected_breakout_room_id": str(breakout_room.id),
            "expected_assignment_revision": help_request.assignment_revision,
        },
        format="json",
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [str(help_request.id)]
    assert ack_response.status_code == 200
    help_request.refresh_from_db()
    assert help_request.status == BreakoutHelpRequest.Status.ACKNOWLEDGED
    assert help_request.acknowledged_at is not None


def test_manager_cannot_acknowledge_help_after_reassignment():
    """A host reaching an old room cannot acknowledge the participant's new alert."""
    room = RoomFactory()
    admin = UserFactory()
    room.accesses.create(user=admin, role=RoleChoices.ADMIN)
    session = BreakoutSessionFactory(
        room=room, status=BreakoutSession.Status.ACTIVE, revision=2
    )
    old_room = BreakoutRoomFactory(session=session)
    new_room = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(
        breakout_room=old_room,
        participant_identity="participant-a",
        participant_name="Alice",
    )
    help_request = BreakoutHelpRequest.objects.create(
        session=session,
        breakout_room=old_room,
        requester_identity="participant-a",
        requester_name="Alice",
        assignment_revision=2,
    )
    with (
        mock.patch.object(BreakoutService, "_reconcile_livekit_assignments"),
        mock.patch("core.services.room_management.RoomManagement.update_metadata"),
    ):
        BreakoutService().assign_participants(
            session,
            {
                str(old_room.id): [],
                str(new_room.id): [{"identity": "participant-a", "name": "Alice"}],
            },
            expected_revision=2,
        )

    client = APIClient()
    client.force_login(admin)
    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/acknowledge-help/",
        {
            "help_request_id": str(help_request.id),
            "expected_breakout_room_id": str(old_room.id),
            "expected_assignment_revision": 2,
        },
        format="json",
    )

    assert response.status_code == 409
    help_request.refresh_from_db()
    assert help_request.breakout_room == new_room
    assert help_request.assignment_revision == 3
    assert help_request.status == BreakoutHelpRequest.Status.OPEN


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
    """A guest with a signed capability can join their assigned breakout room."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.ACTIVE)
    b_room = BreakoutRoomFactory(session=session)
    client = APIClient()
    with mock.patch("core.breakout.services.utils.notify_participants"):
        entry = client.post(
            f"/api/v1.0/rooms/{room.id}/request-entry/",
            {"username": "Anonymous Guest"},
            format="json",
        )
    anon_identity = entry.json()["id"]
    BreakoutAssignment.objects.create(
        breakout_room=b_room,
        participant_identity=anon_identity,
        participant_name="Anonymous Guest",
    )

    url = f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/rooms/{b_room.id}/join/"
    with mock.patch("core.utils.generate_token") as mock_token:
        mock_token.return_value = "mocked-anon-jwt-token"

        resp = client.post(url, {}, format="json")
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
        {"revision": session.revision, "assignments": oversized},
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
            "revision": session.revision,
            "assignments": {
                "00000000-0000-0000-0000-000000000000": [
                    {"identity": "p2", "name": "Ghost"}
                ]
            },
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
