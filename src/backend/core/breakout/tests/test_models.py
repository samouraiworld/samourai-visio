# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,unused-import,line-too-long,unused-variable
"""Unit tests for breakout models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError

import pytest

from core.breakout.models import BreakoutAssignment, BreakoutRoom, BreakoutSession
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
