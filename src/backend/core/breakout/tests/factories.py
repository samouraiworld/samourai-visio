# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,unused-import,line-too-long,unused-variable
"""Factories for breakout models."""

import factory

from core.breakout.models import BreakoutAssignment, BreakoutRoom, BreakoutSession
from core.factories import RoomFactory, UserFactory


class BreakoutSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BreakoutSession

    room = factory.SubFactory(RoomFactory)
    created_by = factory.SubFactory(UserFactory)
    status = BreakoutSession.Status.CONFIGURING
    duration_seconds = 300


class BreakoutRoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BreakoutRoom

    session = factory.SubFactory(BreakoutSessionFactory)
    name = factory.Sequence(lambda n: f"Room {n + 1}")
    livekit_room_name = factory.LazyAttribute(
        lambda obj: BreakoutRoom.generate_livekit_room_name(obj.session.id, obj.order)
    )
    order = factory.Sequence(lambda n: n)


class BreakoutAssignmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BreakoutAssignment

    breakout_room = factory.SubFactory(BreakoutRoomFactory)
    participant_identity = factory.Sequence(lambda n: f"user-identity-{n}")
    participant_name = factory.Sequence(lambda n: f"Participant {n}")
