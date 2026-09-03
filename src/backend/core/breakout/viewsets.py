"""API endpoints for the breakout rooms feature.

Nested under ``/api/v1.0/rooms/{room_id}/breakout-sessions/``.
All endpoints return 404 when the feature flag is disabled.
"""

from logging import getLogger

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404

from rest_framework import decorators, status, viewsets
from rest_framework.response import Response

from core import models as core_models

from .models import BreakoutRoom, BreakoutSession
from .serializers import (
    BreakoutSessionSerializer,
    BreakoutSessionStatusSerializer,
    BroadcastMessageSerializer,
    BulkAssignSerializer,
    CreateBreakoutSessionSerializer,
    JoinBreakoutRoomSerializer,
    UpdateBreakoutSessionSerializer,
)
from .services import (
    BreakoutService,
    BreakoutServiceError,
    InvalidSessionStateError,
    SessionAlreadyActiveError,
)

logger = getLogger(__name__)


def _check_feature_flag():
    """Raise Http404 if the breakout rooms feature flag is disabled."""
    if not getattr(settings, "MEET_BREAKOUT_ROOMS_ENABLED", False):
        raise Http404


class BreakoutSessionViewSet(viewsets.ViewSet):
    """ViewSet for managing breakout sessions within a room.

    Endpoints:
        POST   /rooms/{room_id}/breakout-sessions/           — create
        GET    /rooms/{room_id}/breakout-sessions/            — list (active)
        PATCH  /rooms/{room_id}/breakout-sessions/{sid}/      — activate/close
        GET    /rooms/{room_id}/breakout-sessions/{sid}/status/ — live status
        PUT    /rooms/{room_id}/breakout-sessions/{sid}/assignments/ — bulk assign
        POST   /rooms/{room_id}/breakout-sessions/{sid}/randomize/  — random assign
        POST   /rooms/{room_id}/breakout-sessions/{sid}/rooms/{rid}/join/ — get LK token
    """

    def _get_room(self, room_id):
        """Resolve the parent room and check feature flag."""
        _check_feature_flag()
        try:
            return core_models.Room.objects.get(pk=room_id)
        except (core_models.Room.DoesNotExist, ValidationError, ValueError):
            return get_object_or_404(core_models.Room, slug=room_id)

    def _can_manage(self, room, user):
        return room.is_administrator_or_owner(user)

    def _get_session(self, room_id, session_id):
        """Resolve a breakout session within a room."""
        room = self._get_room(room_id)
        return get_object_or_404(
            BreakoutSession,
            pk=session_id,
            room=room,
        )

    # ── POST /rooms/{room_id}/breakout-sessions/ ──────────────────────

    def create(self, request, room_id=None):
        """Create a new breakout session."""
        room = self._get_room(room_id)

        if not self._can_manage(room, request.user):
            return Response(
                {"detail": "You must be an administrator or owner of the room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CreateBreakoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = BreakoutService().create_session(
                room=room,
                num_rooms=serializer.validated_data["num_rooms"],
                created_by=request.user if request.user.is_authenticated else None,
                duration_seconds=serializer.validated_data.get("duration_seconds"),
                room_names=serializer.validated_data.get("room_names"),
            )
        except SessionAlreadyActiveError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except BreakoutServiceError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = BreakoutSession.objects.prefetch_related(
            "breakout_rooms__assignments"
        ).get(pk=session.pk)
        return Response(
            BreakoutSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )

    # ── GET /rooms/{room_id}/breakout-sessions/ ───────────────────────

    def list(self, request, room_id=None):
        """List active/configuring breakout sessions for a room.

        - Unauthenticated users → 403.
        - Authenticated room members (non-admin) → empty list [].
          Session existence is already visible via LiveKit room metadata;
          this endpoint is the authoritative source for admins only.
        - Admins/owners → full session list with nested rooms and assignments.
        """
        room = self._get_room(room_id)

        if not request.user or not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Non-admin members: return empty list rather than 403 so that
        # useBreakoutSession polling does not permanently fail on reload.
        if not self._can_manage(room, request.user):
            return Response([])

        sessions = BreakoutSession.objects.filter(
            room=room,
            status__in=[
                BreakoutSession.Status.CONFIGURING,
                BreakoutSession.Status.ACTIVE,
            ],
        ).prefetch_related("breakout_rooms__assignments")

        return Response(BreakoutSessionSerializer(sessions, many=True).data)

    # ── PATCH /rooms/{room_id}/breakout-sessions/{sid}/ ───────────────

    def partial_update(self, request, room_id=None, pk=None):
        """Update a session's status (activate or close)."""
        session = self._get_session(room_id, pk)

        if not self._can_manage(session.room, request.user):
            return Response(
                {"detail": "You must be an administrator or owner of the room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UpdateBreakoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_status = serializer.validated_data["status"]
        service = BreakoutService()

        try:
            if target_status == BreakoutSession.Status.ACTIVE:
                session = service.activate_session(session)
            elif target_status == BreakoutSession.Status.CLOSED:
                session = service.close_session(session)
        except InvalidSessionStateError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = BreakoutSession.objects.prefetch_related(
            "breakout_rooms__assignments"
        ).get(pk=session.pk)
        return Response(BreakoutSessionSerializer(session).data)

    # ── GET /rooms/{room_id}/breakout-sessions/{sid}/status/ ──────────

    @decorators.action(detail=True, methods=["get"], url_path="status")
    def live_status(self, request, room_id=None, pk=None):
        """Get live participant counts for all breakout rooms in a session."""
        session = self._get_session(room_id, pk)

        if not self._can_manage(session.room, request.user):
            return Response(
                {"detail": "You must be an administrator or owner of the room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        rooms_status = BreakoutService().get_live_status(session)

        data = {
            "session_id": str(session.id),
            "status": session.status,
            "started_at": session.started_at,
            "duration_seconds": session.duration_seconds,
            "rooms": rooms_status,
        }

        serializer = BreakoutSessionStatusSerializer(data)
        return Response(serializer.data)

    # ── PUT /rooms/{room_id}/breakout-sessions/{sid}/assignments/ ─────

    @decorators.action(detail=True, methods=["put"], url_path="assignments")
    def assignments(self, request, room_id=None, pk=None):
        """Bulk assign participants to breakout rooms."""
        session = self._get_session(room_id, pk)

        if not self._can_manage(session.room, request.user):
            return Response(
                {"detail": "You must be an administrator or owner of the room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = BulkAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            BreakoutService().assign_participants(
                session,
                serializer.validated_data["assignments"],
            )
        except BreakoutServiceError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Return updated session with prefetch
        session = BreakoutSession.objects.prefetch_related(
            "breakout_rooms__assignments"
        ).get(pk=session.pk)
        return Response(BreakoutSessionSerializer(session).data)

    # ── POST /rooms/{room_id}/breakout-sessions/{sid}/randomize/ ──────

    @decorators.action(detail=True, methods=["post"], url_path="randomize")
    def randomize(self, request, room_id=None, pk=None):
        """Randomly distribute participants across breakout rooms."""
        session = self._get_session(room_id, pk)

        if not self._can_manage(session.room, request.user):
            return Response(
                {"detail": "You must be an administrator or owner of the room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        participants = request.data.get("participants", [])
        if not participants:
            return Response(
                {"detail": "No participants provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            BreakoutService().randomize_assignments(session, participants)
        except BreakoutServiceError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = BreakoutSession.objects.prefetch_related(
            "breakout_rooms__assignments"
        ).get(pk=session.pk)
        return Response(BreakoutSessionSerializer(session).data)

    # ── POST /rooms/{room_id}/breakout-sessions/{sid}/broadcast/ ──────

    @decorators.action(detail=True, methods=["post"], url_path="broadcast")
    def broadcast(self, request, room_id=None, pk=None):
        """Broadcast an announcement message to all breakout rooms."""
        session = self._get_session(room_id, pk)

        if not self._can_manage(session.room, request.user):
            return Response(
                {"detail": "You must be an administrator or owner of the room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = BroadcastMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            recipient_count = BreakoutService().broadcast_message(
                session,
                serializer.validated_data["message"],
            )
        except InvalidSessionStateError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "broadcast_sent",
                "recipient_rooms": recipient_count,
            },
            status=status.HTTP_200_OK,
        )

    # ── POST .../breakout-sessions/{sid}/request-help/ ────────────────

    @decorators.action(detail=True, methods=["post"], url_path="request-help")
    def request_help(self, request, room_id=None, pk=None):
        """Send an assistance beacon from a breakout room to the host."""
        session = self._get_session(room_id, pk)
        if not session.is_active:
            return Response(
                {"detail": "Breakout session is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        breakout_room_id = request.data.get("breakout_room_id")
        if not breakout_room_id:
            return Response(
                {"detail": "breakout_room_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        breakout_room = get_object_or_404(
            BreakoutRoom,
            pk=breakout_room_id,
            session=session,
        )

        participant_id = str(request.data.get("participant_id") or "").strip()
        if request.user.is_authenticated and hasattr(request.user, "sub"):
            caller_identity = str(request.user.sub)
        else:
            caller_identity = participant_id

        # Validate caller is assigned to this room or is manager
        is_assigned = (
            breakout_room.assignments.filter(
                participant_identity=caller_identity
            ).exists()
            if caller_identity
            else False
        )
        if not is_assigned and not self._can_manage(session.room, request.user):
            return Response(
                {"detail": "You are not a participant in this breakout room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Rate limiting: 15-second cooldown per caller/IP/room
        client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR", "")
        cache_key = (
            f"breakout_help_cooldown_{session.id}_"
            f"{breakout_room.id}_{client_ip}_{caller_identity}"
        )
        if cache.get(cache_key):
            return Response(
                {"detail": "Please wait before requesting help again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        cache.set(cache_key, True, timeout=15)

        raw_name = request.data.get("participant_name")
        clean_name = str(raw_name).strip()[:64] if raw_name else "A participant"

        BreakoutService().send_help_request(
            session=session,
            breakout_room_id=breakout_room.id,
            participant_name=clean_name,
        )

        return Response({"status": "help_requested"}, status=status.HTTP_200_OK)

    # ── POST .../breakout-sessions/{sid}/rooms/{rid}/join/ ────────────

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path=r"rooms/(?P<breakout_room_id>[^/.]+)/join",
    )
    def join_breakout_room(self, request, room_id=None, pk=None, breakout_room_id=None):
        """Get a LiveKit token for a specific breakout room.

        Requires the participant to be assigned to this breakout room.
        """
        session = self._get_session(room_id, pk)

        if not session.is_active:
            return Response(
                {"detail": "Breakout session is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        breakout_room = get_object_or_404(
            BreakoutRoom,
            pk=breakout_room_id,
            session=session,
        )

        serializer = JoinBreakoutRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Resolve participant identity
        participant_id = serializer.validated_data.get("participant_id")
        username = serializer.validated_data.get("username")
        if request.user.is_anonymous:
            identity = participant_id or username or "guest"
        else:
            identity = str(request.user.sub)

        if not identity:
            return Response(
                {"detail": "Participant identity could not be determined."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check assignment (moderator/admin/owner can join any room)
        is_admin = self._can_manage(session.room, request.user)
        if (
            not is_admin
            and not breakout_room.assignments.filter(
                participant_identity=identity,
            ).exists()
        ):
            return Response(
                {"detail": "You are not assigned to this breakout room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        livekit_data = BreakoutService().generate_breakout_token(
            breakout_room=breakout_room,
            user=request.user,
            username=serializer.validated_data.get("username"),
            participant_id=participant_id,
        )

        return Response({"livekit": livekit_data})
