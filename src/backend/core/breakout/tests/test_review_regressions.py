"""Regression cases for participant boundaries and lifecycle recovery."""

from contextlib import contextmanager
from unittest import mock

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from core.breakout.serializers import BreakoutParticipantSerializer
from core.breakout.services import BreakoutService
from core.breakout.tests.factories import BreakoutSessionFactory
from core.factories import RoomFactory, UserFactory
from core.models import RoleChoices, RoomAccessLevel
from core.services.livekit_events import LiveKitEventsService
from core.services.lobby import LobbyService
from core.services.room_management import RoomManagement

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("identity", [" alice ", "   "])
def test_assignment_preserves_opaque_subject(identity):
    """Whitespace is a valid, significant part of an OIDC subject."""
    serializer = BreakoutParticipantSerializer(data={"identity": identity})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["identity"] == identity


def test_restricted_session_does_not_disclose_announcement_to_outsider():
    """Authentication alone grants no access to a restricted meeting."""
    session = BreakoutSessionFactory(
        room=RoomFactory(access_level=RoomAccessLevel.RESTRICTED),
        status="active",
        last_broadcast_message="Private discussion",
        last_broadcast_at=timezone.now(),
    )
    client = APIClient()
    client.force_login(UserFactory())
    response = client.get(
        f"/api/v1.0/rooms/{session.room_id}/breakout-sessions/"
        f"{session.id}/current-assignment/"
    )
    assert response.status_code == 403
    assert "Private discussion" not in response.content.decode()


@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize("decision,expected", [(None, 403), (False, 403), (True, 200)])
@mock.patch("core.utils.notify_participants")
def test_unassigned_lobby_participant_requires_admission(
    _notify, authenticated, decision, expected
):
    """Signed capabilities prove identity; accepted lobby state grants admission."""
    session = BreakoutSessionFactory(
        room=RoomFactory(access_level=RoomAccessLevel.RESTRICTED),
        status="active",
        last_broadcast_message="Private discussion",
        last_broadcast_at=timezone.now(),
    )
    client = APIClient()
    if authenticated:
        client.force_login(UserFactory())
    entry = client.post(
        f"/api/v1.0/rooms/{session.room_id}/request-entry/",
        {"username": "Visitor"},
        format="json",
    )
    assert entry.status_code == 200
    if decision is not None:
        LobbyService().handle_participant_entry(
            session.room_id, entry.json()["id"], decision
        )
    response = client.get(
        f"/api/v1.0/rooms/{session.room_id}/breakout-sessions/{session.id}/current-assignment/"
    )
    assert response.status_code == expected
    if expected == 200:
        assert response.json()["last_broadcast"]["message"] == "Private discussion"
    else:
        assert "Private discussion" not in response.content.decode()


@pytest.mark.parametrize(
    "field,value",
    [
        ("help_request_id", "invalid"),
        ("expected_breakout_room_id", "invalid"),
        ("expected_assignment_revision", True),
        ("expected_assignment_revision", 1.9),
        ("expected_assignment_revision", -1),
    ],
)
def test_help_acknowledgement_rejects_malformed_input(field, value):
    """Malformed UUIDs and revisions fail validation before database lookup."""
    admin = UserFactory()
    room = RoomFactory(users=[(admin, RoleChoices.ADMIN)])
    session = BreakoutSessionFactory(room=room, status="active")
    client = APIClient()
    client.force_login(admin)
    payload = {
        "help_request_id": str(session.id),
        "expected_breakout_room_id": str(room.id),
        "expected_assignment_revision": 1,
        field: value,
    }
    response = client.post(
        f"/api/v1.0/rooms/{room.id}/breakout-sessions/{session.id}/acknowledge-help/",
        payload,
        format="json",
    )
    assert response.status_code == 400


@mock.patch.object(RoomManagement, "update_metadata")
def test_recreated_main_room_rediscovers_active_session(update_metadata, settings):
    """A fresh main-room connection must discover the persisted session."""
    settings.ROOM_TELEPHONY_ENABLED = False
    settings.ROOMKIT_ENABLED = False
    session = BreakoutSessionFactory(status="active", revision=3)
    event = mock.Mock()
    event.room.name = str(session.room_id)
    LiveKitEventsService()._handle_room_started(event)  # pylint: disable=protected-access
    update_metadata.assert_called_once()
    assert update_metadata.call_args.kwargs["metadata"]["breakout"][
        "session_id"
    ] == str(session.id)


@mock.patch.object(RoomManagement, "update_metadata")
def test_parent_restore_observes_a_close_completed_while_waiting_for_the_lock(
    update_metadata,
):
    """Restoration must read session state after acquiring the effect lock."""
    session = BreakoutSessionFactory(status="active")

    @contextmanager
    def close_before_acquiring(_room_id):
        session.status = "closed"
        session.save()
        yield

    with mock.patch.object(
        BreakoutService, "_room_effect_lock", side_effect=close_before_acquiring
    ):
        BreakoutService().restore_parent_metadata(session.room)
    update_metadata.assert_not_called()
