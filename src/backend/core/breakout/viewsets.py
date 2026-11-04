"""API endpoints for breakout sessions, nested under a meeting."""

from django.shortcuts import get_object_or_404

from rest_framework import response as drf_response
from rest_framework import status as drf_status
from rest_framework import viewsets

from core import models
from core.api.feature_flag import FeatureFlag
from core.services.lobby import LobbyService

from . import serializers, services

ACTIVE = models.BreakoutSessionStatusChoices.ACTIVE


class BreakoutSessionViewSet(viewsets.ViewSet):
    """Open, list and close a meeting's breakout sessions, and move its participants.

    Every action but close answers 404 with the flag off, so a session opened
    before the flag went off can still be closed.
    """

    def _get_room(self, room_id, manage=False):
        room = get_object_or_404(models.Room, pk=room_id)
        if manage and not room.is_administrator_or_owner(self.request.user):
            self.permission_denied(self.request)
        return room

    def _get_assignment(self, room, **filters):
        """The caller's assignment in the meeting's active session, or 404."""
        user = self.request.user
        identity = (
            str(user.sub)
            if user.is_authenticated
            else LobbyService.get_or_create_participant_id(self.request, room.id)
        )
        return get_object_or_404(
            models.BreakoutAssignment.objects.select_related(
                "breakout_room", "session__room"
            ),
            session__room=room,
            session__status=ACTIVE,
            identity=identity,
            **filters,
        )

    @FeatureFlag.require("breakout_rooms")
    def list(self, request, room_id=None):
        """The meeting's active session, as a list of zero or one."""
        room = self._get_room(room_id, manage=True)
        sessions = room.breakout_sessions.filter(status=ACTIVE).prefetch_related(
            "rooms__assignments"
        )
        return drf_response.Response(
            serializers.BreakoutSessionSerializer(sessions, many=True).data
        )

    @FeatureFlag.require("breakout_rooms")
    def create(self, request, room_id=None):
        """Open a session with its rooms and assignments."""
        room = self._get_room(room_id, manage=True)
        serializer = serializers.OpenBreakoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = services.open_session(
            room, request.user, serializer.validated_data["rooms"]
        )
        return drf_response.Response(
            serializers.BreakoutSessionSerializer(session).data,
            status=drf_status.HTTP_201_CREATED,
        )

    def close(self, request, room_id=None, pk=None):
        """Close a session; closing it again answers the same."""
        room = self._get_room(room_id, manage=True)
        session = services.close_session(
            get_object_or_404(room.breakout_sessions, pk=pk)
        )
        return drf_response.Response(
            serializers.BreakoutSessionSerializer(session).data
        )

    @FeatureFlag.require("breakout_rooms")
    def current_assignment(self, request, room_id=None):
        """Where the caller belongs in the active session."""
        assignment = self._get_assignment(self._get_room(room_id))
        return drf_response.Response(
            {
                "session_id": str(assignment.session_id),
                "room": {
                    "id": str(assignment.breakout_room_id),
                    "name": assignment.breakout_room.name,
                },
            }
        )

    @FeatureFlag.require("breakout_rooms")
    def join(self, request, room_id=None, pk=None, room_pk=None):
        """A pass to the breakout room the caller is assigned to."""
        assignment = self._get_assignment(
            self._get_room(room_id), session_id=pk, breakout_room_id=room_pk
        )
        return drf_response.Response(services.join_pass(assignment, request.user))
