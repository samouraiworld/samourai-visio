"""Serializers for breakout sessions."""

# pylint: disable=abstract-method

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from core import models


class BreakoutAssignmentSerializer(serializers.ModelSerializer):
    """A participant assigned to a breakout room."""

    class Meta:
        model = models.BreakoutAssignment
        fields = ["identity", "name"]


class BreakoutRoomSerializer(serializers.ModelSerializer):
    """A breakout room with the participants assigned to it."""

    participants = BreakoutAssignmentSerializer(
        source="assignments", many=True, read_only=True
    )

    class Meta:
        model = models.BreakoutRoom
        fields = ["id", "name", "participants"]


class BreakoutSessionSerializer(serializers.ModelSerializer):
    """A breakout session with its rooms."""

    rooms = BreakoutRoomSerializer(many=True, read_only=True)

    class Meta:
        model = models.BreakoutSession
        fields = ["id", "status", "created_at", "closed_at", "rooms"]


class ParticipantInputSerializer(serializers.Serializer):
    """A participant the host assigns."""

    identity = serializers.CharField(max_length=255, trim_whitespace=False)
    name = serializers.CharField(max_length=255, allow_blank=True)


class RoomInputSerializer(serializers.Serializer):
    """A breakout room the host opens."""

    name = serializers.CharField(max_length=200)
    participants = ParticipantInputSerializer(many=True)


class OpenBreakoutSessionSerializer(serializers.Serializer):
    """The host's split: 2 to 10 rooms, each participant in one of them."""

    rooms = RoomInputSerializer(many=True, min_length=2, max_length=10)

    def validate_rooms(self, rooms):
        """Reject a participant assigned to two rooms."""
        identities = [
            participant["identity"]
            for room in rooms
            for participant in room["participants"]
        ]
        if len(identities) != len(set(identities)):
            raise serializers.ValidationError(
                _("A participant can be assigned to one room only.")
            )
        return rooms
