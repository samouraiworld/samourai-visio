# pylint: disable=too-many-arguments,too-many-positional-arguments,broad-exception-caught,too-many-lines,no-name-in-module,protected-access,too-many-branches
"""Business logic for the breakout rooms feature.

All LiveKit room lifecycle, participant assignment, token generation,
and session state transitions are orchestrated here.  Viewsets should
delegate to this service rather than calling LiveKit directly.
"""

import asyncio
import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
from logging import getLogger
from typing import Dict, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from asgiref.sync import async_to_sync
from livekit.api import (
    CreateRoomRequest,
    DeleteRoomRequest,
    ListParticipantsRequest,
    ListRoomsRequest,
    RoomParticipantIdentity,
)

from core import utils
from core.services.room_management import RoomManagement, RoomNotFoundException

from .models import (
    BreakoutAssignment,
    BreakoutHelpRequest,
    BreakoutRoom,
    BreakoutSession,
)

logger = getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

MAX_ROOMS_PER_SESSION = 10
MIN_ROOMS_PER_SESSION = 2
EMPTY_TIMEOUT_SECONDS = 300  # LiveKit auto-destroys rooms after 5 min empty
BREAKOUT_TOKEN_TTL_SECONDS = 60
MAX_PARTICIPANTS_PER_SESSION = 1000
HELP_REQUEST_COOLDOWN_SECONDS = 15
CLEANUP_LOCK_SECONDS = 300
EFFECT_RETRY_AFTER_SECONDS = 120
EFFECT_LOCK_TIMEOUT_SECONDS = 300
EFFECT_LOCK_WAIT_SECONDS = 10
LIVEKIT_RECONCILIATION_CONCURRENCY = 10
LIVEKIT_RECONCILIATION_TIMEOUT_SECONDS = 30
LIVEKIT_LIFECYCLE_TIMEOUT_SECONDS = 30


def serialize_room_effects(method):
    """Serialize durable state changes and LiveKit effects for one parent room."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        target = args[0] if args else kwargs.get("room") or kwargs.get("session")
        if target is None:
            raise TypeError("A room or breakout session is required.")
        room_id = getattr(target, "room_id", None) or target.pk
        with self._room_effect_lock(room_id):
            return method(self, *args, **kwargs)

    return wrapped


class BreakoutServiceError(Exception):
    """Base exception for breakout service operations."""


class SessionAlreadyActiveError(BreakoutServiceError):
    """Raised when trying to create a session while one is already active."""


class InvalidSessionStateError(BreakoutServiceError):
    """Raised when a state transition is invalid."""


class BreakoutUpstreamError(BreakoutServiceError):
    """Raised when a required LiveKit effect did not complete."""


class HelpRequestRateLimitedError(BreakoutServiceError):
    """Raised when help requests are submitted faster than the allowed rate."""


class BreakoutService:
    """Orchestrates breakout session lifecycle."""

    # ── Session CRUD ───────────────────────────────────────────────────

    @serialize_room_effects
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

        try:
            with transaction.atomic():
                type(room).objects.select_for_update().get(pk=room.pk)
                if BreakoutSession.objects.filter(
                    room=room,
                    status__in=[
                        BreakoutSession.Status.CONFIGURING,
                        BreakoutSession.Status.ACTIVATING,
                        BreakoutSession.Status.ACTIVE,
                        BreakoutSession.Status.CLOSING,
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

                    breakout_rooms.append(
                        BreakoutRoom.objects.create(
                            session=session,
                            name=display_name,
                            livekit_room_name=lk_name,
                            order=i,
                        )
                    )
        except IntegrityError as error:
            raise SessionAlreadyActiveError(
                "This room already has an active or configuring breakout session."
            ) from error

        try:
            self._create_livekit_rooms([br.livekit_room_name for br in breakout_rooms])
        except Exception as error:
            self._record_effect_error(session, error)
            raise BreakoutUpstreamError(
                "Breakout rooms could not be created; the operation can be retried."
            ) from error

        logger.info(
            "Created breakout session %s with %d rooms for room %s",
            session.id,
            num_rooms,
            room.id,
        )

        return session

    @serialize_room_effects
    def activate_session(self, session: BreakoutSession) -> BreakoutSession:
        """Transition a session from CONFIGURING → ACTIVE.

        Updates main room metadata so participants detect the breakout via
        the metadata watcher (source of truth). Also sends a data message
        push notification for speed.

        Raises:
            InvalidSessionStateError: if session is not in CONFIGURING status.
        """
        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            if session.status not in [
                BreakoutSession.Status.CONFIGURING,
                BreakoutSession.Status.ACTIVATING,
            ]:
                raise InvalidSessionStateError(
                    f"Cannot activate session in '{session.status}' status."
                )
            if (
                session.status == BreakoutSession.Status.ACTIVATING
                and not session.effect_error
                and session.updated_at
                > timezone.now() - timedelta(seconds=EFFECT_RETRY_AFTER_SECONDS)
            ):
                raise InvalidSessionStateError(
                    "Breakout activation is already in progress."
                )
            if session.status == BreakoutSession.Status.CONFIGURING:
                session.status = BreakoutSession.Status.ACTIVATING
                session.started_at = timezone.now()
                session.ends_at = (
                    session.started_at + timedelta(seconds=session.duration_seconds)
                    if session.duration_seconds
                    else None
                )
                session.revision += 1
                session.effect_error = ""
                session.save(
                    update_fields=[
                        "status",
                        "started_at",
                        "ends_at",
                        "revision",
                        "effect_error",
                        "updated_at",
                    ]
                )
                session.refresh_from_db()

        breakout_metadata = {"breakout": self._build_breakout_metadata(session)}
        try:
            RoomManagement().update_metadata(
                room_name=str(session.room_id),
                metadata=breakout_metadata,
            )
        except Exception as error:
            self._record_effect_error(session, error)
            raise BreakoutUpstreamError(
                "Breakout activation could not be synchronized; retry activation."
            ) from error

        self._try_send_data_to_room(
            room_name=str(session.room_id),
            data={"type": "breakout:revision", **breakout_metadata["breakout"]},
        )

        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            if (
                session.status != BreakoutSession.Status.ACTIVATING
                or session.revision != breakout_metadata["breakout"]["revision"]
            ):
                raise InvalidSessionStateError(
                    "Breakout activation was superseded by a newer operation."
                )
            session.status = BreakoutSession.Status.ACTIVE
            session.effect_error = ""
            session.save(update_fields=["status", "effect_error", "updated_at"])

        logger.info("Activated breakout session %s", session.id)
        return session

    @serialize_room_effects
    def close_session(self, session: BreakoutSession) -> BreakoutSession:
        """Close a session: recall all participants and destroy breakout rooms.

        1. Sends recall data message to all breakout rooms.
        2. Updates main room metadata (removes breakout state).
        3. Deletes LiveKit breakout rooms (force-disconnects participants).
        4. Updates session status to CLOSED.
        """
        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            if session.is_closed:
                return session
            if session.status not in [
                BreakoutSession.Status.CONFIGURING,
                BreakoutSession.Status.ACTIVATING,
                BreakoutSession.Status.ACTIVE,
                BreakoutSession.Status.CLOSING,
            ]:
                raise InvalidSessionStateError(
                    f"Cannot close session in '{session.status}' status."
                )
            if (
                session.status == BreakoutSession.Status.CLOSING
                and not session.effect_error
                and session.updated_at
                > timezone.now() - timedelta(seconds=EFFECT_RETRY_AFTER_SECONDS)
            ):
                raise InvalidSessionStateError("Breakout close is already in progress.")
            if session.status != BreakoutSession.Status.CLOSING:
                session.status = BreakoutSession.Status.CLOSING
                session.revision += 1
                session.effect_error = ""
                session.save(
                    update_fields=[
                        "status",
                        "revision",
                        "effect_error",
                        "updated_at",
                    ]
                )
                session.refresh_from_db()

        breakout_rooms = list(session.breakout_rooms.all())
        try:
            # Removing the authoritative parent-room metadata is required and
            # idempotent. Do it before deleting ephemeral rooms so a retry can
            # never be blocked by an advisory message to an already-gone room.
            try:
                RoomManagement().update_metadata(
                    room_name=str(session.room_id),
                    remove_keys=["breakout"],
                )
            except RoomNotFoundException:
                logger.info(
                    "Parent LiveKit room %s is already absent during breakout close",
                    session.room_id,
                )
            self._try_send_data_to_rooms(
                [room.livekit_room_name for room in breakout_rooms],
                {
                    "type": "breakout:recall",
                    "main_room": str(session.room_id),
                    "session_id": str(session.id),
                    "revision": session.revision,
                },
            )
            self._delete_livekit_rooms(
                [breakout_room.livekit_room_name for breakout_room in breakout_rooms]
            )
        except Exception as error:
            self._record_effect_error(session, error)
            raise BreakoutUpstreamError(
                "Breakout close could not be completed; retry close."
            ) from error

        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            if session.status != BreakoutSession.Status.CLOSING:
                raise InvalidSessionStateError(
                    "Breakout close was superseded by a newer operation."
                )
            session.status = BreakoutSession.Status.CLOSED
            session.closed_at = timezone.now()
            session.effect_error = ""
            session.save(
                update_fields=["status", "closed_at", "effect_error", "updated_at"]
            )

        logger.info("Closed breakout session %s", session.id)
        return session

    # ── Assignments ────────────────────────────────────────────────────

    @serialize_room_effects
    def assign_participants(  # noqa: PLR0912
        self,
        session: BreakoutSession,
        assignments: Dict[str, Dict],
        expected_revision: Optional[int] = None,
    ) -> None:
        """Bulk assign participants to breakout rooms.

        ``assignments`` is a dict mapping ``breakout_room_id`` (str UUID)
        to a list of ``{identity, name}`` dicts.

        Clears existing assignments and recreates from scratch (idempotent).

        Raises:
            BreakoutServiceError: if a participant is assigned to multiple rooms.
        """
        # Normalize and validate no duplicate identities across rooms
        all_identities = set()
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
                all_identities.add(identity)
                normalized_list.append({"identity": identity, "name": name})
            normalized_assignments[room_id] = normalized_list

        if len(all_identities) > MAX_PARTICIPANTS_PER_SESSION:
            raise BreakoutServiceError(
                "The assignment payload exceeds the participant limit."
            )

        with transaction.atomic():
            session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
            if expected_revision is not None and session.revision != expected_revision:
                raise InvalidSessionStateError(
                    "Breakout session changed; refresh assignments and try again."
                )
            if session.status in [
                BreakoutSession.Status.CLOSING,
                BreakoutSession.Status.CLOSED,
            ]:
                raise InvalidSessionStateError(
                    "Cannot assign participants while a session is closing or closed."
                )

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

            BreakoutAssignment.objects.filter(session=session).delete()

            new_assignment_by_identity = {}
            for room_id_str, participants in normalized_assignments.items():
                breakout_room = resolved_rooms[room_id_str]

                BreakoutAssignment.objects.bulk_create(
                    [
                        BreakoutAssignment(
                            session=session,
                            breakout_room=breakout_room,
                            participant_identity=p["identity"],
                            participant_name=p["name"],
                        )
                        for p in participants
                    ]
                )
                for participant in participants:
                    new_assignment_by_identity[participant["identity"]] = (
                        breakout_room,
                        participant["name"],
                    )
            session.revision += 1
            session.effect_error = ""
            session.save(update_fields=["revision", "effect_error", "updated_at"])
            session.refresh_from_db()

            self._reconcile_open_help_requests(session, new_assignment_by_identity)

        # If session is active, evict old connections and publish a bounded revision.
        if session.is_active:
            try:
                # Reconcile the durable assignment first. Parent-room metadata can
                # legitimately be absent once everyone has moved to breakouts.
                self._reconcile_livekit_assignments(session)
                self._publish_revision(session)
            except Exception as error:
                self._record_effect_error(session, error)
                raise BreakoutUpstreamError(
                    "Assignments were saved but LiveKit reconciliation failed; retry."
                ) from error

        logger.info(
            "Assigned %d participants across breakout rooms for session %s",
            len(all_identities),
            session.id,
        )

    def randomize_assignments(
        self,
        session: BreakoutSession,
        participants: List[Dict[str, str]],
        expected_revision: Optional[int] = None,
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

        self.assign_participants(
            session, assignments, expected_revision=expected_revision
        )
        return assignments

    # ── Live Status ────────────────────────────────────────────────────

    def get_live_status(self, session: BreakoutSession) -> List[Dict]:
        """Query LiveKit for participant counts in each breakout room."""
        rooms = list(session.breakout_rooms.all())
        return self._fetch_live_status(rooms)

    @async_to_sync
    async def get_main_room_status(self, session: BreakoutSession) -> Dict:
        """Return authoritative parent-room presence or an unknown state."""
        lkapi = utils.create_livekit_client()
        try:
            response = await lkapi.room.list_participants(
                ListParticipantsRequest(room=str(session.room_id))
            )
            participants = [
                {"identity": participant.identity, "name": participant.name}
                for participant in response.participants
            ]
            return {
                "participant_count": len(participants),
                "participants": participants,
                "connection_status": "available",
            }
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to list participants for main room %s", session.room_id
            )
            return {
                "participant_count": None,
                "participants": [],
                "connection_status": "unknown",
            }
        finally:
            await lkapi.aclose()

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
                connection_status = "available"
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to list participants for breakout room %s",
                    br.livekit_room_name,
                )
                participants = []
                connection_status = "unknown"

            return {
                "id": str(br.id),
                "name": br.name,
                "livekit_room_name": br.livekit_room_name,
                "order": br.order,
                "participant_count": (
                    len(participants) if connection_status == "available" else None
                ),
                "participants": participants,
                "connection_status": connection_status,
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
        identity: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Dict:
        """Generate a LiveKit token for a breakout room.

        Breakout room tokens have reduced permissions: no ``room_admin``.
        """
        if user is None:
            user = AnonymousUser()

        if not identity:
            raise BreakoutServiceError("Participant identity could not be determined.")

        ttl_seconds = BREAKOUT_TOKEN_TTL_SECONDS
        if breakout_room.session.ends_at:
            remaining = int(
                (breakout_room.session.ends_at - timezone.now()).total_seconds()
            )
            if remaining <= 0:
                raise InvalidSessionStateError("Breakout session has ended.")
            ttl_seconds = min(ttl_seconds, remaining)

        token = utils.generate_token(
            room=breakout_room.livekit_room_name,
            user=user,
            username=display_name,
            role="member",  # No admin in breakout rooms
            participant_id=identity,
            ttl=timedelta(seconds=ttl_seconds),
            can_publish_data=True,
            sources=breakout_room.session.room.configuration.get(
                "can_publish_sources", None
            ),
        )

        configuration = settings.LIVEKIT_CONFIGURATION
        return {
            "url": configuration["url"],
            "room": breakout_room.livekit_room_name,
            "token": token,
        }

    # ── Cleanup ────────────────────────────────────────────────────────

    def cleanup_stale_sessions(self) -> int:
        """Auto-close sessions at their absolute deadline and retry failed closes.

        Returns the number of sessions reconciled.
        """
        now = timezone.now()
        retry_before = now - timedelta(seconds=EFFECT_RETRY_AFTER_SECONDS)
        candidate_ids = BreakoutSession.objects.filter(
            Q(
                status=BreakoutSession.Status.ACTIVE,
                ends_at__isnull=False,
                ends_at__lte=now,
            )
            | Q(
                status=BreakoutSession.Status.CLOSING,
                effect_error__gt="",
            )
            | Q(
                status=BreakoutSession.Status.CLOSING,
                updated_at__lte=retry_before,
            )
            | Q(
                status=BreakoutSession.Status.ACTIVATING,
                effect_error__gt="",
            )
            | Q(
                status=BreakoutSession.Status.ACTIVATING,
                updated_at__lte=retry_before,
            )
            | Q(
                status=BreakoutSession.Status.ACTIVE,
                effect_error__gt="",
            )
        ).values_list("id", flat=True)

        reconciled_count = 0
        for session_id in candidate_ids:
            lock_key = f"breakout-cleanup:{session_id}"
            if not cache.add(lock_key, "1", timeout=CLEANUP_LOCK_SECONDS):
                continue
            try:
                session = BreakoutSession.objects.get(pk=session_id)
                logger.info("Reconciling breakout session %s", session.id)
                if session.status == BreakoutSession.Status.ACTIVATING:
                    self.activate_session(session)
                elif session.status == BreakoutSession.Status.ACTIVE:
                    if session.ends_at is not None and session.ends_at <= now:
                        self.close_session(session)
                    else:
                        self.retry_session(session)
                else:
                    self.close_session(session)
                reconciled_count += 1
            except (
                BreakoutSession.DoesNotExist,
                BreakoutUpstreamError,
                InvalidSessionStateError,
            ):
                logger.warning("Breakout session %s remains retryable", session_id)
            finally:
                cache.delete(lock_key)

        return reconciled_count

    def retry_session(self, session: BreakoutSession) -> BreakoutSession:
        """Retry the required effect for a session in a recoverable state."""
        session.refresh_from_db()
        if (
            session.status == BreakoutSession.Status.CONFIGURING
            and session.effect_error
        ):
            with self._room_effect_lock(session.room_id):
                session.refresh_from_db()
                if not (
                    session.status == BreakoutSession.Status.CONFIGURING
                    and session.effect_error
                ):
                    raise InvalidSessionStateError(
                        "Breakout creation retry was superseded by a newer operation."
                    )
                try:
                    self._create_livekit_rooms(
                        list(
                            session.breakout_rooms.values_list(
                                "livekit_room_name", flat=True
                            )
                        )
                    )
                except Exception as error:
                    self._record_effect_error(session, error)
                    raise BreakoutUpstreamError(
                        "Breakout rooms could not be created; retry later."
                    ) from error
                session.effect_error = ""
                session.save(update_fields=["effect_error", "updated_at"])
                return session
        if session.status == BreakoutSession.Status.ACTIVATING:
            return self.activate_session(session)
        if session.status == BreakoutSession.Status.CLOSING:
            return self.close_session(session)
        if session.status == BreakoutSession.Status.ACTIVE and session.effect_error:
            with self._room_effect_lock(session.room_id):
                session.refresh_from_db()
                if not (
                    session.status == BreakoutSession.Status.ACTIVE
                    and session.effect_error
                ):
                    raise InvalidSessionStateError(
                        "Breakout reconciliation retry was superseded."
                    )
                try:
                    self._reconcile_livekit_assignments(session)
                    self._publish_revision(session)
                except Exception as error:
                    self._record_effect_error(session, error)
                    raise BreakoutUpstreamError(
                        "Breakout assignments could not be reconciled; retry later."
                    ) from error
                session.effect_error = ""
                session.save(update_fields=["effect_error", "updated_at"])
                return session
        raise InvalidSessionStateError(
            f"Session in '{session.status}' status has no retryable effect."
        )

    # ── Private Helpers ────────────────────────────────────────────────

    @staticmethod
    @contextmanager
    def _room_effect_lock(room_id):
        """Hold the cross-worker lock that orders DB state and LiveKit effects."""
        lock = cache.lock(
            f"breakout-effects:{room_id}",
            timeout=EFFECT_LOCK_TIMEOUT_SECONDS,
            blocking_timeout=EFFECT_LOCK_WAIT_SECONDS,
        )
        if not lock.acquire(blocking=True):
            raise InvalidSessionStateError(
                "Another breakout room operation is still in progress."
            )
        try:
            yield
        finally:
            try:
                lock.release()
            except Exception:
                logger.exception(
                    "Breakout effect lock %s could not be released", room_id
                )

    def _build_breakout_metadata(self, session: BreakoutSession) -> dict:
        """Build bounded, non-sensitive shared metadata."""
        return {
            "session_id": str(session.id),
            "status": (
                BreakoutSession.Status.ACTIVE
                if session.status == BreakoutSession.Status.ACTIVATING
                else session.status
            ),
            "started_at": (
                session.started_at.isoformat() if session.started_at else None
            ),
            "ends_at": session.ends_at.isoformat() if session.ends_at else None,
            "duration_seconds": session.duration_seconds,
            "revision": session.revision,
        }

    def _publish_revision(self, session: BreakoutSession) -> None:
        """Publish only a revision hint; clients fetch scoped state from the API."""
        summary = self._build_breakout_metadata(session)
        try:
            RoomManagement().update_metadata(
                room_name=str(session.room_id),
                metadata={"breakout": summary},
            )
        except RoomNotFoundException:
            logger.info(
                "Parent LiveKit room %s is absent; clients will poll breakout revision",
                session.room_id,
            )
        payload = {"type": "breakout:revision", **summary}
        self._try_send_data_to_rooms(
            [str(session.room_id)]
            + list(session.breakout_rooms.values_list("livekit_room_name", flat=True)),
            payload,
        )

    @staticmethod
    def _reconcile_open_help_requests(
        session: BreakoutSession,
        assignments: Dict[str, tuple[BreakoutRoom, str]],
    ) -> None:
        """Move open help with its requester, or cancel it when unassigned."""
        open_help_requests = list(
            BreakoutHelpRequest.objects.select_for_update().filter(
                session=session,
                status=BreakoutHelpRequest.Status.OPEN,
            )
        )
        cancelled_at = timezone.now()
        for help_request in open_help_requests:
            new_assignment = assignments.get(help_request.requester_identity)
            if new_assignment is None:
                help_request.status = BreakoutHelpRequest.Status.CANCELLED
                help_request.cancelled_at = cancelled_at
                help_request.save(
                    update_fields=["status", "cancelled_at", "updated_at"]
                )
                continue
            breakout_room, participant_name = new_assignment
            help_request.breakout_room = breakout_room
            help_request.requester_name = participant_name
            help_request.assignment_revision = session.revision
            help_request.save(
                update_fields=[
                    "breakout_room",
                    "requester_name",
                    "assignment_revision",
                    "updated_at",
                ]
            )

    @staticmethod
    def _record_effect_error(session: BreakoutSession, error: Exception) -> None:
        """Persist a bounded retryable effect error for operator visibility."""
        effect_error = str(error)[:2000] or error.__class__.__name__
        updated = BreakoutSession.objects.filter(
            pk=session.pk,
            status=session.status,
            revision=session.revision,
        ).update(effect_error=effect_error, updated_at=timezone.now())
        if updated:
            session.effect_error = effect_error

    @async_to_sync
    async def _create_livekit_rooms(self, room_names: List[str]) -> None:
        """Create LiveKit rooms with empty_timeout for auto-cleanup."""
        lkapi = utils.create_livekit_client()
        created = []
        try:
            async with asyncio.timeout(LIVEKIT_LIFECYCLE_TIMEOUT_SECONDS):
                response = await lkapi.room.list_rooms(
                    ListRoomsRequest(names=room_names)
                )
                existing = {room.name for room in response.rooms}

                async def create_room(name):
                    await lkapi.room.create_room(
                        CreateRoomRequest(
                            name=name,
                            empty_timeout=EMPTY_TIMEOUT_SECONDS,
                        )
                    )
                    created.append(name)

                await asyncio.gather(
                    *[create_room(name) for name in room_names if name not in existing]
                )
        except Exception:
            results = await asyncio.gather(
                *[
                    lkapi.room.delete_room(DeleteRoomRequest(room=name))
                    for name in created
                ],
                return_exceptions=True,
            )
            for name, result in zip(created, results, strict=True):
                if isinstance(result, Exception):
                    logger.error("Failed to compensate LiveKit room %s", name)
            raise
        finally:
            await lkapi.aclose()

    @async_to_sync
    async def _delete_livekit_rooms(self, room_names: List[str]) -> None:
        """Idempotently delete LiveKit rooms and disconnect their participants."""
        lkapi = utils.create_livekit_client()
        try:
            async with asyncio.timeout(LIVEKIT_LIFECYCLE_TIMEOUT_SECONDS):
                response = await lkapi.room.list_rooms(
                    ListRoomsRequest(names=room_names)
                )
                existing = {room.name for room in response.rooms}
                await asyncio.gather(
                    *[
                        lkapi.room.delete_room(DeleteRoomRequest(room=name))
                        for name in room_names
                        if name in existing
                    ]
                )
        finally:
            await lkapi.aclose()

    @async_to_sync
    async def _remove_participant(self, room_name: str, identity: str) -> None:
        """Remove an identity from its previous LiveKit room if still connected."""
        lkapi = utils.create_livekit_client()
        try:
            participants = await lkapi.room.list_participants(
                ListParticipantsRequest(room=room_name)
            )
            if any(
                participant.identity == identity
                for participant in participants.participants
            ):
                await lkapi.room.remove_participant(
                    RoomParticipantIdentity(room=room_name, identity=identity)
                )
        finally:
            await lkapi.aclose()

    def _reconcile_livekit_assignments(self, session: BreakoutSession) -> None:
        """Evict participants connected to a non-authoritative breakout room."""
        authoritative_rooms = dict(
            session.assignments.values_list(
                "participant_identity", "breakout_room__livekit_room_name"
            )
        )
        manager_identities = set(
            session.room.accesses.filter(
                role__in=["administrator", "owner"]
            ).values_list("user__sub", flat=True)
        )
        rooms = list(session.breakout_rooms.values_list("livekit_room_name", flat=True))
        self._reconcile_livekit_participants(
            authoritative_rooms, manager_identities, rooms
        )

    @staticmethod
    @async_to_sync
    async def _reconcile_livekit_participants(
        authoritative_rooms: Dict[str, str],
        manager_identities: set[str],
        rooms: List[str],
    ) -> None:
        """Apply an authorization snapshot with bounded LiveKit concurrency."""
        lkapi = utils.create_livekit_client()
        semaphore = asyncio.Semaphore(LIVEKIT_RECONCILIATION_CONCURRENCY)

        async def list_participants(room_name):
            async with semaphore:
                return await lkapi.room.list_participants(
                    ListParticipantsRequest(room=room_name)
                )

        async def remove_participant(room_name, identity):
            async with semaphore:
                await lkapi.room.remove_participant(
                    RoomParticipantIdentity(room=room_name, identity=identity)
                )

        try:
            async with asyncio.timeout(LIVEKIT_RECONCILIATION_TIMEOUT_SECONDS):
                responses = await asyncio.gather(
                    *[list_participants(room_name) for room_name in rooms]
                )
                removals = [
                    remove_participant(room_name, participant.identity)
                    for room_name, response in zip(rooms, responses, strict=True)
                    for participant in response.participants
                    if participant.identity not in manager_identities
                    and authoritative_rooms.get(participant.identity) != room_name
                ]
                await asyncio.gather(*removals)
        finally:
            await lkapi.aclose()

    def enforce_breakout_participant_access(
        self, room_name: str, identity: str
    ) -> bool:
        """Enforce the current assignment when LiveKit accepts a participant.

        Join JWTs cannot be revoked after issuance. The authenticated LiveKit
        webhook is therefore the post-admission guard for cached tokens.
        """
        breakout_room = (
            BreakoutRoom.objects.select_related("session__room")
            .filter(livekit_room_name=room_name)
            .first()
        )
        authorized = False
        if breakout_room and breakout_room.session.is_active:
            authorized = BreakoutAssignment.objects.filter(
                session=breakout_room.session,
                breakout_room=breakout_room,
                participant_identity=identity,
            ).exists()
            if not authorized:
                user = get_user_model().objects.filter(sub=identity).first()
                authorized = bool(
                    user and breakout_room.session.room.is_administrator_or_owner(user)
                )

        if not authorized:
            self._remove_participant(room_name, identity)
        return authorized

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
        try:
            self._send_data_to_rooms(
                [br.livekit_room_name for br in rooms] + [str(session.room_id)],
                payload,
            )
        except Exception as error:
            raise BreakoutUpstreamError(
                "The announcement could not be delivered; retry it."
            ) from error

        logger.info(
            "Broadcast announcement sent to %d breakout rooms for session %s",
            len(rooms),
            session.id,
        )
        return len(rooms)

    def create_help_request(
        self,
        session: BreakoutSession,
        identity: str,
    ) -> tuple[BreakoutHelpRequest, bool]:
        """Create or return the caller's single authoritative open request."""
        identity_digest = hashlib.sha256(identity.encode()).hexdigest()
        rate_key = f"breakout-help:{session.id}:{identity_digest}"
        try:
            with transaction.atomic():
                session = BreakoutSession.objects.select_for_update().get(pk=session.pk)
                if not session.is_active:
                    raise InvalidSessionStateError(
                        "Breakout session is no longer active."
                    )
                assignment = BreakoutAssignment.objects.select_related(
                    "breakout_room"
                ).get(
                    session=session,
                    participant_identity=identity,
                )
                existing = BreakoutHelpRequest.objects.filter(
                    session=session,
                    requester_identity=identity,
                    status=BreakoutHelpRequest.Status.OPEN,
                ).first()
                if existing:
                    return existing, False
                if not cache.add(rate_key, "1", timeout=HELP_REQUEST_COOLDOWN_SECONDS):
                    raise HelpRequestRateLimitedError(
                        "Please wait before requesting help again."
                    )
                help_request, created = BreakoutHelpRequest.objects.get_or_create(
                    session=session,
                    requester_identity=identity,
                    status=BreakoutHelpRequest.Status.OPEN,
                    defaults={
                        "breakout_room": assignment.breakout_room,
                        "requester_name": assignment.participant_name,
                        "assignment_revision": session.revision,
                    },
                )
        except IntegrityError:
            help_request = BreakoutHelpRequest.objects.get(
                session=session,
                requester_identity=identity,
                status=BreakoutHelpRequest.Status.OPEN,
            )
            created = False

        if created:
            payload = {
                "type": "breakout:help_revision",
                "session_id": str(session.id),
                "help_request_id": str(help_request.id),
                "revision": session.revision,
            }
            self._try_send_data_to_rooms(
                [str(session.room_id)]
                + [
                    breakout_room.livekit_room_name
                    for breakout_room in session.breakout_rooms.all()
                ],
                payload,
            )
        return help_request, created

    def _send_data_to_room(self, room_name: str, data: dict) -> None:
        """Send a reliable data message to all participants in a room."""
        utils.notify_participants(room_name, data)

    def _send_data_to_rooms(self, room_names: List[str], data: dict) -> None:
        """Deliver required messages concurrently within each request timeout."""
        if not room_names:
            return
        with ThreadPoolExecutor(
            max_workers=min(len(room_names), MAX_ROOMS_PER_SESSION + 1)
        ) as executor:
            futures = [
                executor.submit(self._send_data_to_room, room_name, data)
                for room_name in room_names
            ]
            errors = [error for future in futures if (error := future.exception())]
        if errors:
            raise errors[0]

    def _try_send_data_to_room(self, room_name: str, data: dict) -> None:
        """Send an advisory message without making durable state depend on it."""
        try:
            self._send_data_to_room(room_name, data)
        except Exception:  # noqa: BLE001
            logger.warning("Breakout data hint could not be sent to room %s", room_name)

    def _try_send_data_to_rooms(self, room_names: List[str], data: dict) -> None:
        """Deliver advisory hints concurrently within each request timeout."""
        if not room_names:
            return
        with ThreadPoolExecutor(
            max_workers=min(len(room_names), MAX_ROOMS_PER_SESSION + 1)
        ) as executor:
            list(
                executor.map(
                    lambda name: self._try_send_data_to_room(name, data), room_names
                )
            )
