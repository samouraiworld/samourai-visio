# pylint: disable=too-many-arguments,too-many-positional-arguments,broad-exception-caught,too-many-lines,no-name-in-module
"""Business logic for the breakout rooms feature.

All LiveKit room lifecycle, participant assignment, token generation,
and session state transitions are orchestrated here.  Viewsets should
delegate to this service rather than calling LiveKit directly.
"""

import asyncio
import random
from datetime import timedelta
from logging import getLogger
from typing import Dict, List, Optional

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.utils import timezone

from asgiref.sync import async_to_sync
from livekit.api import (
    CreateRoomRequest,
    DeleteRoomRequest,
    ListParticipantsRequest,
)

from core import utils
from core.services.room_management import (
    RoomManagement,
    RoomManagementException,
)

from .models import BreakoutAssignment, BreakoutRoom, BreakoutSession

logger = getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

MAX_ROOMS_PER_SESSION = 10
MIN_ROOMS_PER_SESSION = 2
EMPTY_TIMEOUT_SECONDS = 300  # LiveKit auto-destroys rooms after 5 min empty
GRACE_PERIOD_SECONDS = 300  # Auto-close stale sessions after this grace period


class BreakoutServiceError(Exception):
    """Base exception for breakout service operations."""


class SessionAlreadyActiveError(BreakoutServiceError):
    """Raised when trying to create a session while one is already active."""


class InvalidSessionStateError(BreakoutServiceError):
    """Raised when a state transition is invalid."""


class BreakoutService:
    """Orchestrates breakout session lifecycle."""

    # ── Session CRUD ───────────────────────────────────────────────────

    def create_session(
        self,
        room,
        num_rooms: int,
        created_by,
        duration_seconds: Optional[int] = None,
        room_names: Optional[List[str]] = None,
    ) -> BreakoutSession:
        """Create a breakout session with *num_rooms* ephemeral rooms.

        Creates LiveKit rooms immediately so they're ready when activated.

        Raises:
            SessionAlreadyActiveError: if the room already has a non-closed session.
            BreakoutServiceError: on LiveKit or validation errors.
        """
        num_rooms = max(MIN_ROOMS_PER_SESSION, min(num_rooms, MAX_ROOMS_PER_SESSION))

        with transaction.atomic():
            # Enforce one-active-session-per-room at service level (DB constraint is backup)
            if BreakoutSession.objects.filter(
                room=room,
                status__in=[
                    BreakoutSession.Status.CONFIGURING,
                    BreakoutSession.Status.ACTIVE,
                ],
            ).exists():
                raise SessionAlreadyActiveError(
                    "This room already has an active or configuring breakout session."
                )

            session = BreakoutSession.objects.create(
                room=room,
                created_by=created_by,
                duration_seconds=duration_seconds,
            )

            breakout_rooms = []
            for i in range(num_rooms):
                display_name = (
                    room_names[i]
                    if room_names and i < len(room_names)
                    else f"Room {i + 1}"
                )
                lk_name = BreakoutRoom.generate_livekit_room_name(session.id, i)

                br = BreakoutRoom.objects.create(
                    session=session,
                    name=display_name,
                    livekit_room_name=lk_name,
                    order=i,
                )
                breakout_rooms.append(br)

            # Pre-create LiveKit rooms inside atomic transaction
            self._create_livekit_rooms([br.livekit_room_name for br in breakout_rooms])

        logger.info(
            "Created breakout session %s with %d rooms for room %s",
            session.id,
            num_rooms,
            room.id,
        )

        return session

    def activate_session(self, session: BreakoutSession) -> BreakoutSession:
        """Transition a session from CONFIGURING → ACTIVE.

        Updates main room metadata so participants detect the breakout via
        the metadata watcher (source of truth). Also sends a data message
        push notification for speed.

        Raises:
            InvalidSessionStateError: if session is not in CONFIGURING status.
        """
        if not session.is_configuring:
            raise InvalidSessionStateError(
                f"Cannot activate session in '{session.status}' status."
            )

        session.status = BreakoutSession.Status.ACTIVE
        session.started_at = timezone.now()
        session.save(update_fields=["status", "started_at", "updated_at"])

        # Build assignment map for metadata
        assignments = self._build_assignment_map(session)

        # Update main room metadata (SOURCE OF TRUTH)
        breakout_metadata = {
            "breakout": {
                "session_id": str(session.id),
                "status": "active",
                "started_at": session.started_at.isoformat(),
                "duration_seconds": session.duration_seconds,
                "assignments": assignments,
                "rooms": [
                    {
                        "id": str(br.id),
                        "name": br.name,
                        "livekit_room_name": br.livekit_room_name,
                        "order": br.order,
                    }
                    for br in session.breakout_rooms.all()
                ],
            }
        }

        try:
            RoomManagement().update_metadata(
                room_name=str(session.room_id),
                metadata=breakout_metadata,
            )
        except RoomManagementException:
            logger.exception(
                "Failed to update main room metadata for breakout session %s",
                session.id,
            )

        # Send push data message (SPEED OPTIMIZATION — not source of truth)
        self._send_data_to_room(
            room_name=str(session.room_id),
            data={"type": "breakout:activate", **breakout_metadata["breakout"]},
        )

        logger.info("Activated breakout session %s", session.id)
        return session

    def close_session(self, session: BreakoutSession) -> BreakoutSession:
        """Close a session: recall all participants and destroy breakout rooms.

        1. Sends recall data message to all breakout rooms.
        2. Updates main room metadata (removes breakout state).
        3. Deletes LiveKit breakout rooms (force-disconnects participants).
        4. Updates session status to CLOSED.
        """
        if session.is_closed:
            return session

        session.status = BreakoutSession.Status.CLOSED
        session.closed_at = timezone.now()
        session.save(update_fields=["status", "closed_at", "updated_at"])

        # Send recall to all breakout rooms
        breakout_rooms = session.breakout_rooms.all()
        for br in breakout_rooms:
            self._send_data_to_room(
                room_name=br.livekit_room_name,
                data={"type": "breakout:recall", "main_room": str(session.room_id)},
            )

        # Clear breakout metadata from main room
        try:
            RoomManagement().update_metadata(
                room_name=str(session.room_id),
                remove_keys=["breakout"],
            )
        except RoomManagementException:
            logger.exception(
                "Failed to clear breakout metadata for room %s", session.room_id
            )

        # Destroy LiveKit rooms (forces disconnect for any remaining participants)
        self._delete_livekit_rooms([br.livekit_room_name for br in breakout_rooms])

        logger.info("Closed breakout session %s", session.id)
        return session

    # ── Assignments ────────────────────────────────────────────────────

    def assign_participants(
        self,
        session: BreakoutSession,
        assignments: Dict[str, Dict],
    ) -> None:
        """Bulk assign participants to breakout rooms.

        ``assignments`` is a dict mapping ``breakout_room_id`` (str UUID)
        to a list of ``{identity, name}`` dicts.

        Clears existing assignments and recreates from scratch (idempotent).

        Raises:
            BreakoutServiceError: if a participant is assigned to multiple rooms.
        """
        if session.is_closed:
            raise InvalidSessionStateError(
                "Cannot assign participants to a closed session."
            )

        # Normalize and validate no duplicate identities across rooms
        all_identities = []
        normalized_assignments = {}
        for room_id, participants in assignments.items():
            normalized_list = []
            for p in participants:
                if isinstance(p, str):
                    identity = p
                    name = ""
                elif isinstance(p, dict):
                    identity = p.get("identity", "")
                    name = p.get("name", "")
                else:
                    continue

                if not identity:
                    continue

                if identity in all_identities:
                    raise BreakoutServiceError(
                        f"Participant '{identity}' is assigned to multiple rooms."
                    )
                all_identities.append(identity)
                normalized_list.append({"identity": identity, "name": name})
            normalized_assignments[room_id] = normalized_list

        with transaction.atomic():
            # Prefetch all rooms in one query, then validate IDs.
            # A single unknown ID must abort the whole operation and leave
            # existing assignments intact (Bug 3 fix — N-queries → 1 query).
            session_rooms = {str(r.id): r for r in session.breakout_rooms.all()}
            resolved_rooms = {}
            for room_id_str in normalized_assignments:
                if room_id_str not in session_rooms:
                    raise BreakoutServiceError(
                        f"Breakout room {room_id_str} does not belong to this session."
                    )
                resolved_rooms[room_id_str] = session_rooms[room_id_str]

            # Clear and rebuild atomically
            BreakoutAssignment.objects.filter(
                breakout_room__session=session,
            ).delete()

            for room_id_str, participants in normalized_assignments.items():
                breakout_room = resolved_rooms[room_id_str]

                BreakoutAssignment.objects.bulk_create(
                    [
                        BreakoutAssignment(
                            breakout_room=breakout_room,
                            participant_identity=p["identity"],
                            participant_name=p["name"],
                        )
                        for p in participants
                    ]
                )

        # If session is active, update metadata with new assignments
        if session.is_active:
            self._update_assignment_metadata(session)

        logger.info(
            "Assigned %d participants across breakout rooms for session %s",
            len(all_identities),
            session.id,
        )

    def randomize_assignments(
        self,
        session: BreakoutSession,
        participants: List[Dict[str, str]],
    ) -> Dict[str, List]:
        """Distribute participants evenly across rooms and persist assignments.

        Returns the generated assignment map.
        """
        rooms = list(session.breakout_rooms.order_by("order"))
        if not rooms:
            raise BreakoutServiceError("Session has no breakout rooms.")

        shuffled = list(participants)
        random.shuffle(shuffled)

        assignments = {str(r.id): [] for r in rooms}
        for i, participant in enumerate(shuffled):
            target_room = rooms[i % len(rooms)]
            assignments[str(target_room.id)].append(participant)

        self.assign_participants(session, assignments)
        return assignments

    # ── Live Status ────────────────────────────────────────────────────

    def get_live_status(self, session: BreakoutSession) -> List[Dict]:
        """Query LiveKit for participant counts in each breakout room."""
        rooms = list(session.breakout_rooms.all())
        return self._fetch_live_status(rooms)

    @async_to_sync
    async def _fetch_live_status(self, rooms: List[BreakoutRoom]) -> List[Dict]:
        """Query LiveKit for participant counts — all rooms concurrently."""
        lkapi = utils.create_livekit_client()

        async def fetch_one(br: BreakoutRoom) -> Dict:
            try:
                response = await lkapi.room.list_participants(
                    ListParticipantsRequest(room=br.livekit_room_name)
                )
                participants = [
                    {"identity": p.identity, "name": p.name}
                    for p in response.participants
                ]
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to list participants for breakout room %s",
                    br.livekit_room_name,
                )
                participants = []

            return {
                "id": str(br.id),
                "name": br.name,
                "livekit_room_name": br.livekit_room_name,
                "order": br.order,
                "participant_count": len(participants),
                "participants": participants,
            }

        try:
            results = await asyncio.gather(*[fetch_one(br) for br in rooms])
        finally:
            await lkapi.aclose()

        return list(results)

    # ── Token Generation ───────────────────────────────────────────────

    def generate_breakout_token(
        self,
        breakout_room: BreakoutRoom,
        user=None,
        username: Optional[str] = None,
        participant_id: Optional[str] = None,
    ) -> Dict:
        """Generate a LiveKit token for a breakout room.

        Breakout room tokens have reduced permissions: no ``room_admin``.
        """
        if user is None:
            user = AnonymousUser()

        ttl = None
        if breakout_room.session.duration_seconds:
            ttl = timedelta(
                seconds=breakout_room.session.duration_seconds + GRACE_PERIOD_SECONDS
            )

        token = utils.generate_token(
            room=breakout_room.livekit_room_name,
            user=user,
            username=username,
            role="member",  # No admin in breakout rooms
            participant_id=participant_id,
            ttl=ttl,
        )

        configuration = settings.LIVEKIT_CONFIGURATION
        return {
            "url": configuration["url"],
            "room": breakout_room.livekit_room_name,
            "token": token,
        }

    # ── Cleanup ────────────────────────────────────────────────────────

    def cleanup_stale_sessions(self) -> int:
        """Auto-close sessions that exceeded their duration + grace period.

        Returns the number of sessions closed.
        """
        now = timezone.now()
        stale_sessions = BreakoutSession.objects.filter(
            status=BreakoutSession.Status.ACTIVE,
            started_at__isnull=False,
        )

        closed_count = 0
        for session in stale_sessions:
            duration = session.duration_seconds or 0
            deadline = session.started_at + timedelta(
                seconds=duration + GRACE_PERIOD_SECONDS
            )
            if now > deadline:
                logger.info(
                    "Auto-closing stale breakout session %s (started %s, duration %ds)",
                    session.id,
                    session.started_at,
                    duration,
                )
                self.close_session(session)
                closed_count += 1

        return closed_count

    def close_sessions_for_room(self, room_id) -> int:
        """Close all active/configuring breakout sessions for a room.

        Called when the main room's LiveKit room finishes (all participants left).
        """
        sessions = BreakoutSession.objects.filter(
            room_id=room_id,
            status__in=[
                BreakoutSession.Status.CONFIGURING,
                BreakoutSession.Status.ACTIVE,
            ],
        )

        closed_count = 0
        for session in sessions:
            self.close_session(session)
            closed_count += 1

        return closed_count

    # ── Private Helpers ────────────────────────────────────────────────

    def _build_assignment_map(self, session: BreakoutSession) -> Dict:
        """Build a participant_identity → room info mapping for metadata."""
        assignments = {}
        for br in session.breakout_rooms.prefetch_related("assignments").all():
            for a in br.assignments.all():
                assignments[a.participant_identity] = {
                    "breakout_room_id": str(br.id),
                    "breakout_room_name": br.name,
                    "livekit_room_name": br.livekit_room_name,
                }
        return assignments

    def _build_breakout_metadata(
        self, session: BreakoutSession, assignments: dict
    ) -> dict:
        """Build the complete breakout blob for LiveKit room metadata.

        Always includes session_id, status, started_at, duration_seconds, rooms,
        and assignments so that a top-level merge in RoomManagement.update_metadata
        never silently drops fields that useBreakoutMetadataWatcher gates on.
        """
        return {
            "session_id": str(session.id),
            "status": session.status,
            "started_at": (
                session.started_at.isoformat() if session.started_at else None
            ),
            "duration_seconds": session.duration_seconds,
            "rooms": [
                {
                    "id": str(br.id),
                    "name": br.name,
                    "livekit_room_name": br.livekit_room_name,
                    "order": br.order,
                }
                for br in session.breakout_rooms.order_by("order")
            ],
            "assignments": assignments,
        }

    def _update_assignment_metadata(self, session: BreakoutSession) -> None:
        """Push the full breakout blob to main room metadata after an assignment change.

        Publishes the complete blob (not just assignments) so that the top-level
        merge in RoomManagement.update_metadata never clobbers status, session_id,
        rooms, or timing fields that the frontend watcher relies on.
        """
        assignments = self._build_assignment_map(session)
        full_breakout = self._build_breakout_metadata(session, assignments)
        try:
            RoomManagement().update_metadata(
                room_name=str(session.room_id),
                metadata={"breakout": full_breakout},
            )
        except RoomManagementException:
            logger.exception(
                "Failed to update assignment metadata for session %s", session.id
            )

    @async_to_sync
    async def _create_livekit_rooms(self, room_names: List[str]) -> None:
        """Create LiveKit rooms with empty_timeout for auto-cleanup."""
        lkapi = utils.create_livekit_client()
        try:
            for name in room_names:
                try:
                    await lkapi.room.create_room(
                        CreateRoomRequest(
                            name=name,
                            empty_timeout=EMPTY_TIMEOUT_SECONDS,
                        )
                    )
                except Exception:
                    logger.exception("Failed to create LiveKit room %s", name)
        finally:
            await lkapi.aclose()

    @async_to_sync
    async def _delete_livekit_rooms(self, room_names: List[str]) -> None:
        """Delete LiveKit rooms, force-disconnecting any remaining participants."""
        lkapi = utils.create_livekit_client()
        try:
            for name in room_names:
                try:
                    await lkapi.room.delete_room(DeleteRoomRequest(room=name))
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to delete LiveKit room %s", name)
        finally:
            await lkapi.aclose()

    def broadcast_message(self, session: BreakoutSession, message: str) -> int:
        """Broadcast an announcement message to all breakout rooms and the parent room.

        Returns the number of recipient breakout rooms.
        """
        if not session.is_active:
            raise InvalidSessionStateError("Cannot broadcast to an inactive session.")

        payload = {
            "type": "breakout:broadcast",
            "message": message,
            "session_id": str(session.id),
        }

        rooms = list(session.breakout_rooms.all())
        for br in rooms:
            self._send_data_to_room(br.livekit_room_name, payload)

        # Also send to parent main room
        self._send_data_to_room(str(session.room_id), payload)

        logger.info(
            "Broadcast announcement sent to %d breakout rooms for session %s",
            len(rooms),
            session.id,
        )
        return len(rooms)

    def send_help_request(
        self,
        session: BreakoutSession,
        breakout_room_id: Optional[str],
        participant_name: str,
    ) -> str:
        """Send an assistance alert from a breakout room to the main room."""
        room_name = "Breakout Room"
        if breakout_room_id:
            try:
                br = session.breakout_rooms.get(id=breakout_room_id)
                room_name = br.name
            except BreakoutRoom.DoesNotExist:
                pass

        payload = {
            "type": "breakout:help_request",
            "breakout_room_id": str(breakout_room_id) if breakout_room_id else "",
            "room_name": room_name,
            "participant_name": participant_name,
            "session_id": str(session.id),
        }

        self._send_data_to_room(str(session.room_id), payload)
        return room_name

    def _send_data_to_room(self, room_name: str, data: dict) -> None:
        """Send a reliable data message to all participants in a room."""
        try:
            utils.notify_participants(room_name, data)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to send data message to room %s", room_name)
