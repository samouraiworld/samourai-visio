"""API endpoints for the breakout rooms feature.

Nested under ``/api/v1.0/rooms/{room_id}/breakout-sessions/``.
Only session creation and activation are gated by the feature flag; open
sessions stay manageable.
"""

from logging import getLogger

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import decorators, exceptions, status, viewsets
from rest_framework.response import Response

from core import models as core_models
from core.api.feature_flag import FeatureFlag
from core.services.lobby import LobbyService

from .models import (
    BreakoutAssignment,
    BreakoutHelpRequest,
    BreakoutRoom,
    BreakoutSession,
)
from .serializers import (
    AcknowledgeHelpSerializer,
    BreakoutHelpRequestSerializer,
    BreakoutSessionSerializer,
    BreakoutSessionStatusSerializer,
    BroadcastMessageSerializer,
    BulkAssignSerializer,
    CreateBreakoutSessionSerializer,
    JoinBreakoutRoomSerializer,
    RandomizeAssignmentsSerializer,
    UpdateBreakoutSessionSerializer,
)
from .services import (
    BreakoutService,
    BreakoutServiceError,
    BreakoutUpstreamError,
    HelpRequestRateLimitedError,
    InvalidSessionStateError,
    SessionAlreadyActiveError,
)

logger = getLogger(__name__)


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

    lookup_value_converter = "uuid"

    def handle_exception(self, exc):
        """Translate domain failures once, keeping services independent of HTTP."""
        if isinstance(exc, BreakoutServiceError):
            status_code = {
                SessionAlreadyActiveError: status.HTTP_409_CONFLICT,
                InvalidSessionStateError: status.HTTP_409_CONFLICT,
                BreakoutUpstreamError: status.HTTP_503_SERVICE_UNAVAILABLE,
                HelpRequestRateLimitedError: status.HTTP_429_TOO_MANY_REQUESTS,
            }.get(type(exc), status.HTTP_400_BAD_REQUEST)
            # Preserve the existing status-update and broadcast API contract.
            if isinstance(exc, InvalidSessionStateError) and self.action in {
                "partial_update",
                "broadcast",
            }:
                status_code = status.HTTP_400_BAD_REQUEST
            return Response({"detail": str(exc)}, status=status_code)
        return super().handle_exception(exc)

    def _require_manager(self, room, user):
        if not self._can_manage(room, user):
            raise exceptions.PermissionDenied(
                "You must be an administrator or owner of the room."
            )

    def _get_room(self, room_id):
        """Resolve the parent room by primary key (the URL only matches a UUID)."""
        return get_object_or_404(core_models.Room, pk=room_id)

    def _can_manage(self, room, user):
        return room.is_administrator_or_owner(user)

    @staticmethod
    def _caller_identity(request, room):
        """Resolve identity only from authenticated or signed server state."""
        if request.user and request.user.is_authenticated:
            return str(request.user.sub)
        return LobbyService.get_participant_id(request, room.id)

    def _get_session(self, room_id, session_id):
        """Resolve a breakout session within a room."""
        room = self._get_room(room_id)
        return get_object_or_404(
            BreakoutSession,
            pk=session_id,
            room=room,
        )

    # ── POST /rooms/{room_id}/breakout-sessions/ ──────────────────────

    @FeatureFlag.require("breakout_rooms")
    def create(self, request, room_id=None):
        """Create a new breakout session."""
        room = self._get_room(room_id)

        self._require_manager(room, request.user)

        serializer = CreateBreakoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = BreakoutService().create_session(
            room=room,
            num_rooms=serializer.validated_data["num_rooms"],
            created_by=request.user if request.user.is_authenticated else None,
            duration_seconds=serializer.validated_data.get("duration_seconds"),
            room_names=serializer.validated_data.get("room_names"),
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
            status__in=BreakoutSession.OPEN_STATUSES,
        ).prefetch_related("breakout_rooms__assignments")

        return Response(BreakoutSessionSerializer(sessions, many=True).data)

    # ── PATCH /rooms/{room_id}/breakout-sessions/{sid}/ ───────────────

    def partial_update(self, request, room_id=None, pk=None):
        """Update a session's status (activate or close)."""
        session = self._get_session(room_id, pk)

        self._require_manager(session.room, request.user)

        serializer = UpdateBreakoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_status = serializer.validated_data["status"]
        if (
            target_status == BreakoutSession.Status.ACTIVE
            and not FeatureFlag.flag_is_active("breakout_rooms")
        ):
            # Activation starts a new live session; it needs the scheduler the
            # flag guarantees. Closing and retrying never do.
            raise Http404
        service = BreakoutService()

        if target_status == BreakoutSession.Status.ACTIVE:
            session = service.activate_session(session)
        elif target_status == BreakoutSession.Status.CLOSED:
            session = service.close_session(session)

        session = BreakoutSession.objects.prefetch_related(
            "breakout_rooms__assignments"
        ).get(pk=session.pk)
        return Response(BreakoutSessionSerializer(session).data)

    @decorators.action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, room_id=None, pk=None):
        """Retry a failed LiveKit effect without duplicating domain state."""
        session = self._get_session(room_id, pk)
        self._require_manager(session.room, request.user)
        session = BreakoutService().retry_session(session)
        return Response(BreakoutSessionSerializer(session).data)

    # ── GET /rooms/{room_id}/breakout-sessions/{sid}/status/ ──────────

    @decorators.action(
        detail=True, methods=["get"], url_path="status", url_name="status"
    )
    def live_status(self, request, room_id=None, pk=None):
        """Get live participant counts for all breakout rooms in a session."""
        session = self._get_session(room_id, pk)

        self._require_manager(session.room, request.user)

        service = BreakoutService()
        rooms_status = service.get_live_status(session)

        data = {
            "session_id": str(session.id),
            "status": session.status,
            "started_at": session.started_at,
            "ends_at": session.ends_at,
            "duration_seconds": session.duration_seconds,
            "main_room": service.get_main_room_status(session),
            "rooms": rooms_status,
        }

        serializer = BreakoutSessionStatusSerializer(data)
        return Response(serializer.data)

    # ── PUT /rooms/{room_id}/breakout-sessions/{sid}/assignments/ ─────

    @decorators.action(detail=True, methods=["put"], url_path="assignments")
    def assignments(self, request, room_id=None, pk=None):
        """Bulk assign participants to breakout rooms."""
        session = self._get_session(room_id, pk)

        self._require_manager(session.room, request.user)

        serializer = BulkAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        BreakoutService().assign_participants(
            session,
            serializer.validated_data["assignments"],
            expected_revision=serializer.validated_data["revision"],
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

        self._require_manager(session.room, request.user)

        serializer = RandomizeAssignmentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        BreakoutService().randomize_assignments(
            session,
            serializer.validated_data["participants"],
            expected_revision=serializer.validated_data["revision"],
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

        self._require_manager(session.room, request.user)

        serializer = BroadcastMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        recipient_count = BreakoutService().broadcast_message(
            session,
            serializer.validated_data["message"],
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
        """Create the caller's durable assistance request."""
        session = self._get_session(room_id, pk)
        if not session.is_active:
            return Response(
                {"detail": "Breakout session is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        caller_identity = self._caller_identity(request, session.room)
        if not caller_identity:
            return Response(
                {"detail": "You are not a participant in this breakout room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            help_request, created = BreakoutService().create_help_request(
                session=session,
                identity=caller_identity,
            )
        except BreakoutAssignment.DoesNotExist:
            return Response(
                {"detail": "You are not a participant in this breakout room."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            BreakoutHelpRequestSerializer(help_request).data,
            status=(status.HTTP_201_CREATED if created else status.HTTP_200_OK),
        )

    @decorators.action(detail=True, methods=["get"], url_path="help-requests")
    def help_requests(self, request, room_id=None, pk=None):
        """List durable open help requests for an authorized manager."""
        session = self._get_session(room_id, pk)
        self._require_manager(session.room, request.user)
        requests = session.help_requests.filter(
            status=BreakoutHelpRequest.Status.OPEN
        ).select_related("breakout_room")
        return Response(BreakoutHelpRequestSerializer(requests, many=True).data)

    @decorators.action(detail=True, methods=["post"], url_path="cancel-help")
    def cancel_help(self, request, room_id=None, pk=None):
        """Cancel the caller's open help request."""
        session = self._get_session(room_id, pk)
        caller_identity = self._caller_identity(request, session.room)
        if not caller_identity:
            return Response(status=status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            help_request = get_object_or_404(
                BreakoutHelpRequest.objects.select_for_update(),
                session=session,
                requester_identity=caller_identity,
                status=BreakoutHelpRequest.Status.OPEN,
            )
            help_request.status = BreakoutHelpRequest.Status.CANCELLED
            help_request.cancelled_at = timezone.now()
            help_request.save(update_fields=["status", "cancelled_at", "updated_at"])
        return Response(BreakoutHelpRequestSerializer(help_request).data)

    @decorators.action(detail=True, methods=["post"], url_path="acknowledge-help")
    def acknowledge_help(self, request, room_id=None, pk=None):
        """Acknowledge one help request as a manager."""
        session = self._get_session(room_id, pk)
        self._require_manager(session.room, request.user)
        serializer = AcknowledgeHelpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expected_room_id = serializer.validated_data["expected_breakout_room_id"]
        expected_revision = serializer.validated_data["expected_assignment_revision"]
        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            help_request = get_object_or_404(
                BreakoutHelpRequest.objects.select_for_update(),
                pk=serializer.validated_data["help_request_id"],
                session=session,
                status=BreakoutHelpRequest.Status.OPEN,
            )
            if (
                not session.is_active
                or str(help_request.breakout_room_id) != str(expected_room_id)
                or help_request.assignment_revision != expected_revision
            ):
                return Response(
                    {"detail": "The help request assignment has changed."},
                    status=status.HTTP_409_CONFLICT,
                )
            help_request.status = BreakoutHelpRequest.Status.ACKNOWLEDGED
            help_request.acknowledged_at = timezone.now()
            help_request.save(update_fields=["status", "acknowledged_at", "updated_at"])
        return Response(BreakoutHelpRequestSerializer(help_request).data)

    @decorators.action(detail=True, methods=["get"], url_path="current-assignment")
    def current_assignment(self, request, room_id=None, pk=None):
        """Return only the caller's current assignment and session revision."""
        session = self._get_session(room_id, pk)
        caller_identity = self._caller_identity(request, session.room)
        if not caller_identity:
            return Response(status=status.HTTP_403_FORBIDDEN)
        assignment = (
            BreakoutAssignment.objects.filter(
                session=session,
                participant_identity=caller_identity,
            )
            .select_related("breakout_room")
            .first()
        )
        if not assignment and not LobbyService().can_access_room(session.room, request):
            return Response(status=status.HTTP_403_FORBIDDEN)
        assignment_data = None
        if assignment:
            assignment_data = {
                "breakout_room_id": str(assignment.breakout_room_id),
                "breakout_room_name": assignment.breakout_room.name,
                "livekit_room_name": assignment.breakout_room.livekit_room_name,
            }
        open_help_request = (
            BreakoutHelpRequest.objects.filter(
                session=session,
                requester_identity=caller_identity,
                status=BreakoutHelpRequest.Status.OPEN,
            )
            .select_related("breakout_room")
            .first()
        )
        return Response(
            {
                "session_id": str(session.id),
                "revision": session.revision,
                "status": session.status,
                "started_at": session.started_at,
                "ends_at": session.ends_at,
                "duration_seconds": session.duration_seconds,
                "last_broadcast": (
                    {
                        "message": session.last_broadcast_message,
                        "sent_at": session.last_broadcast_at,
                    }
                    if session.last_broadcast_at
                    else None
                ),
                "assignment": assignment_data,
                "help_request": (
                    BreakoutHelpRequestSerializer(open_help_request).data
                    if open_help_request
                    else None
                ),
            }
        )

    # ── POST .../breakout-sessions/{sid}/rooms/{rid}/join/ ────────────

    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="rooms/<uuid:breakout_room_id>/join",
        url_name="room-join",
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

        JoinBreakoutRoomSerializer(data=request.data).is_valid(raise_exception=True)
        identity = self._caller_identity(request, session.room)
        if not identity:
            return Response(
                {"detail": "You are not assigned to this breakout room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check assignment (moderator/admin/owner can join any room)
        is_admin = self._can_manage(session.room, request.user)
        assignment = BreakoutAssignment.objects.filter(
            session=session,
            breakout_room=breakout_room,
            participant_identity=identity,
        ).first()
        if not is_admin and assignment is None:
            return Response(
                {"detail": "You are not assigned to this breakout room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        display_name = (
            assignment.participant_name
            if assignment
            else (request.user.full_name or str(request.user))
        )
        livekit_data = BreakoutService().generate_breakout_token(
            breakout_room=breakout_room,
            user=request.user,
            identity=identity,
            display_name=display_name,
        )

        return Response({"livekit": livekit_data})
