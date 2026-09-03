# pylint: disable=abstract-method
"""DRF serializers for the breakout rooms feature."""

from rest_framework import serializers

from .models import BreakoutAssignment, BreakoutRoom, BreakoutSession


class BreakoutAssignmentSerializer(serializers.ModelSerializer):
    """Serialize a single participant assignment."""

    class Meta:
        model = BreakoutAssignment
        fields = ["id", "participant_identity", "participant_name"]
        read_only_fields = ["id"]


class BreakoutRoomSerializer(serializers.ModelSerializer):
    """Serialize a breakout room with its assignments."""

    assignments = BreakoutAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = BreakoutRoom
        fields = ["id", "name", "livekit_room_name", "order", "assignments"]
        read_only_fields = ["id", "livekit_room_name"]


class BreakoutSessionSerializer(serializers.ModelSerializer):
    """Serialize a breakout session with nested rooms."""

    breakout_rooms = BreakoutRoomSerializer(many=True, read_only=True)

    class Meta:
        model = BreakoutSession
        fields = [
            "id",
            "status",
            "duration_seconds",
            "started_at",
            "closed_at",
            "created_at",
            "breakout_rooms",
        ]
        read_only_fields = ["id", "status", "started_at", "closed_at", "created_at"]


class CreateBreakoutSessionSerializer(serializers.Serializer):
    """Input serializer for creating a breakout session."""

    num_rooms = serializers.IntegerField(min_value=2, max_value=10)
    duration_seconds = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=60,
        max_value=28800,  # Max 8 hours (all-day workshops)
    )
    room_names = serializers.ListField(
        child=serializers.CharField(max_length=200),
        required=False,
        allow_empty=True,
    )


class UpdateBreakoutSessionSerializer(serializers.Serializer):
    """Input serializer for updating a session's status."""

    status = serializers.ChoiceField(
        choices=[
            BreakoutSession.Status.ACTIVE,
            BreakoutSession.Status.CLOSED,
        ]
    )


class BulkAssignSerializer(serializers.Serializer):
    """Input serializer for bulk assigning participants.

    Expected format::

        {
            "assignments": {
                "<breakout_room_id>": [
                    {"identity": "user-sub-or-uuid", "name": "Display Name"},
                    ...
                ],
                ...
            }
        }
    """

    assignments = serializers.DictField(
        child=serializers.ListField(
            child=serializers.DictField(
                child=serializers.CharField(max_length=255),
            ),
        ),
    )

    def validate_assignments(self, value):
        """Enforce size bounds and reject unexpected participant dict keys."""
        # Hard cap: sessions allow at most 10 rooms
        if len(value) > 10:
            raise serializers.ValidationError(
                f"Too many rooms in assignment payload: {len(value)} (max 10)."
            )

        allowed_keys = {"identity", "name"}
        for room_id, participants in value.items():
            # Cap participants per room
            if len(participants) > 500:
                raise serializers.ValidationError(
                    f"Room '{room_id}' has {len(participants)} participants (max 500)."
                )
            for idx, participant in enumerate(participants):
                extra = set(participant.keys()) - allowed_keys
                if extra:
                    raise serializers.ValidationError(
                        f"Participant at room '{room_id}' index {idx} contains "
                        f"unexpected keys: {sorted(extra)}. "
                        f"Only 'identity' and 'name' are allowed."
                    )
        return value


class JoinBreakoutRoomSerializer(serializers.Serializer):
    """Input serializer for joining a breakout room."""

    username = serializers.CharField(required=False, default="", allow_blank=True)
    participant_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Stable identity for anonymous participants (from sessionStorage).",
    )


class BreakoutRoomStatusSerializer(serializers.Serializer):
    """Output serializer for live breakout room status."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    livekit_room_name = serializers.CharField()
    order = serializers.IntegerField()
    participant_count = serializers.IntegerField()
    participants = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField())
    )


class BreakoutSessionStatusSerializer(serializers.Serializer):
    """Output serializer for live session status (with participant counts)."""

    session_id = serializers.UUIDField()
    status = serializers.CharField()
    started_at = serializers.DateTimeField()
    duration_seconds = serializers.IntegerField(allow_null=True)
    rooms = BreakoutRoomStatusSerializer(many=True)


class BroadcastMessageSerializer(serializers.Serializer):
    """Input serializer for broadcasting an announcement to all breakout rooms."""

    message = serializers.CharField(max_length=500, min_length=1)
