"""API endpoints for the breakout rooms feature.

Nested under ``/api/v1.0/rooms/{room_id}/breakout-sessions/``.
All endpoints return 404 when the feature flag is disabled.
"""

from logging import getLogger

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import decorators, status, viewsets
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


def _check_feature_flag():
    """Raise Http404 if the breakout rooms feature flag is disabled."""
    if not FeatureFlag.flag_is_active("breakout_rooms"):
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
        except BreakoutUpstreamError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except InvalidSessionStateError as e:
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
                BreakoutSession.Status.ACTIVATING,
                BreakoutSession.Status.ACTIVE,
                BreakoutSession.Status.CLOSING,
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
        except BreakoutUpstreamError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        session = BreakoutSession.objects.prefetch_related(
            "breakout_rooms__assignments"
        ).get(pk=session.pk)
        return Response(BreakoutSessionSerializer(session).data)

    @decorators.action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, room_id=None, pk=None):
        """Retry a failed LiveKit effect without duplicating domain state."""
        session = self._get_session(room_id, pk)
        if not self._can_manage(session.room, request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            session = BreakoutService().retry_session(session)
        except InvalidSessionStateError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        except BreakoutUpstreamError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
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
                expected_revision=serializer.validated_data["revision"],
            )
        except BreakoutUpstreamError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except InvalidSessionStateError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_409_CONFLICT,
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

        serializer = RandomizeAssignmentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            BreakoutService().randomize_assignments(
                session,
                serializer.validated_data["participants"],
                expected_revision=serializer.validated_data["revision"],
            )
        except BreakoutUpstreamError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except InvalidSessionStateError as e:
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
        except BreakoutUpstreamError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
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
        except InvalidSessionStateError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_409_CONFLICT,
            )
        except HelpRequestRateLimitedError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return Response(
            BreakoutHelpRequestSerializer(help_request).data,
            status=(status.HTTP_201_CREATED if created else status.HTTP_200_OK),
        )

    @decorators.action(detail=True, methods=["get"], url_path="help-requests")
    def help_requests(self, request, room_id=None, pk=None):
        """List durable open help requests for an authorized manager."""
        session = self._get_session(room_id, pk)
        if not self._can_manage(session.room, request.user):
            return Response(
                {"detail": "You must be an administrator or owner of the room."},
                status=status.HTTP_403_FORBIDDEN,
            )
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
        help_request = get_object_or_404(
            BreakoutHelpRequest,
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
        if not self._can_manage(session.room, request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)
        expected_room_id = request.data.get("expected_breakout_room_id")
        try:
            expected_revision = int(request.data["expected_assignment_revision"])
        except (KeyError, TypeError, ValueError):
            return Response(
                {"detail": "The expected help assignment is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not expected_room_id:
            return Response(
                {"detail": "The expected help assignment is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            help_request = get_object_or_404(
                BreakoutHelpRequest.objects.select_for_update(),
                pk=request.data.get("help_request_id"),
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
        try:
            livekit_data = BreakoutService().generate_breakout_token(
                breakout_room=breakout_room,
                user=request.user,
                identity=identity,
                display_name=display_name,
            )
        except InvalidSessionStateError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        return Response({"livekit": livekit_data})
