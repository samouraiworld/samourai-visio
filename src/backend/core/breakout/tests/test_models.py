# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,unused-import,line-too-long,unused-variable
"""Unit tests for breakout models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

import pytest

from core.breakout.models import (
    BreakoutAssignment,
    BreakoutHelpRequest,
    BreakoutRoom,
    BreakoutSession,
)
from core.breakout.tests.factories import (
    BreakoutAssignmentFactory,
    BreakoutRoomFactory,
    BreakoutSessionFactory,
)
from core.factories import RoomFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_breakout_session_properties():
    """Verify state boolean properties on BreakoutSession."""
    session = BreakoutSessionFactory(status=BreakoutSession.Status.CONFIGURING)
    assert session.is_configuring is True
    assert session.is_active is False
    assert session.is_closed is False

    session.status = BreakoutSession.Status.ACTIVE
    assert session.is_configuring is False
    assert session.is_active is True
    assert session.is_closed is False

    session.status = BreakoutSession.Status.CLOSED
    assert session.is_configuring is False
    assert session.is_active is False
    assert session.is_closed is True


def test_breakout_session_str():
    """Verify string representation of BreakoutSession."""
    session = BreakoutSessionFactory()
    assert str(session) == f"BreakoutSession({session.room_id}, configuring)"


def test_one_active_session_per_room_constraint():
    """A room cannot have more than one active/configuring session."""
    room = RoomFactory()
    BreakoutSessionFactory(room=room, status=BreakoutSession.Status.CONFIGURING)

    # Attempting to create another configuring session should fail
    with pytest.raises((IntegrityError, ValidationError)):
        BreakoutSession.objects.create(
            room=room,
            status=BreakoutSession.Status.CONFIGURING,
        )

    # Attempting to create an active session for the same room should fail
    with pytest.raises((IntegrityError, ValidationError)):
        BreakoutSession.objects.create(
            room=room,
            status=BreakoutSession.Status.ACTIVE,
        )


def test_multiple_closed_sessions_allowed():
    """A room can have multiple closed sessions."""
    room = RoomFactory()
    s1 = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.CLOSED)
    s2 = BreakoutSessionFactory(room=room, status=BreakoutSession.Status.CLOSED)

    assert BreakoutSession.objects.filter(room=room).count() == 2
    assert s1.id != s2.id


def test_breakout_room_creation_and_str():
    """Verify BreakoutRoom creation, naming, and str representation."""
    session = BreakoutSessionFactory()
    lk_name = BreakoutRoom.generate_livekit_room_name(session.id, 0)
    assert lk_name == f"breakout_{session.id}_0"

    room = BreakoutRoomFactory(
        session=session,
        name="Team Alpha",
        livekit_room_name=lk_name,
        order=0,
    )
    assert str(room) == f"Team Alpha ({lk_name})"


def test_breakout_assignment_creation_and_str():
    """Verify BreakoutAssignment fields and str representation."""
    assignment = BreakoutAssignmentFactory(
        participant_identity="usr_12345",
        participant_name="Alice Smith",
    )
    assert str(assignment) == f"Alice Smith → {assignment.breakout_room.name}"

    # Fallback to identity if name is blank
    assignment_anon = BreakoutAssignmentFactory(
        participant_identity="anon_uuid",
        participant_name="",
    )
    assert str(assignment_anon) == f"anon_uuid → {assignment_anon.breakout_room.name}"


def test_cascade_deletion():
    """Deleting a parent Room cascades to BreakoutSession, Rooms, and Assignments."""
    room = RoomFactory()
    session = BreakoutSessionFactory(room=room)
    br = BreakoutRoomFactory(session=session)
    assignment = BreakoutAssignmentFactory(breakout_room=br)

    room.delete()
    assert BreakoutSession.objects.filter(id=session.id).exists() is False
    assert BreakoutRoom.objects.filter(id=br.id).exists() is False
    assert BreakoutAssignment.objects.filter(id=assignment.id).exists() is False


def test_assignment_identity_is_unique_across_rooms_in_session():
    """The database enforces one authoritative room per participant."""
    session = BreakoutSessionFactory()
    first_room = BreakoutRoomFactory(session=session)
    second_room = BreakoutRoomFactory(session=session)
    BreakoutAssignmentFactory(
        breakout_room=first_room,
        participant_identity="participant-1",
    )

    with pytest.raises((IntegrityError, ValidationError)), transaction.atomic():
        BreakoutAssignmentFactory(
            breakout_room=second_room,
            participant_identity="participant-1",
        )


def test_assignment_rejects_room_from_another_session():
    """The application boundary rejects inconsistent denormalized session data."""
    session = BreakoutSessionFactory()
    other_room = BreakoutRoomFactory()

    with pytest.raises(ValidationError):
        BreakoutAssignment.objects.create(
            session=session,
            breakout_room=other_room,
            participant_identity="participant-1",
        )


def test_only_one_open_help_request_per_participant():
    """Concurrent assistance requests cannot create duplicate open work."""
    assignment = BreakoutAssignmentFactory(participant_identity="participant-1")
    values = {
        "session": assignment.session,
        "breakout_room": assignment.breakout_room,
        "requester_identity": assignment.participant_identity,
    }
    BreakoutHelpRequest.objects.create(**values)

    with pytest.raises((IntegrityError, ValidationError)), transaction.atomic():
        BreakoutHelpRequest.objects.create(**values)


def test_help_request_rejects_room_from_another_session():
    """A durable help request cannot reference another session's room."""
    session = BreakoutSessionFactory()
    other_room = BreakoutRoomFactory()

    with pytest.raises(ValidationError):
        BreakoutHelpRequest.objects.create(
            session=session,
            breakout_room=other_room,
            requester_identity="participant",
        )
