"""Open and close breakout sessions, keeping the media server in step with the database."""

# pylint: disable=no-name-in-module

import asyncio
import contextlib
import json
from datetime import timedelta
from logging import getLogger
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from asgiref.sync import async_to_sync
from livekit.api import (
    CreateRoomRequest,
    DeleteRoomRequest,
    ListRoomsRequest,
    TwirpError,
    UpdateRoomMetadataRequest,
)
from rest_framework import exceptions

from core import models, utils
from core.services.lobby import LobbyService

logger = getLogger(__name__)

METADATA_KEY = "breakout"
MEDIA_SERVER_TIMEOUT_SECONDS = 5
# How long the media server keeps a breakout room nobody has joined yet.
EMPTY_TIMEOUT_SECONDS = 300
# Closing deletes the rooms, and an unspent pass could recreate one until it expires.
JOIN_TOKEN_TTL = timedelta(seconds=60)


class SessionAlreadyActive(exceptions.APIException):
    """The meeting already has an active breakout session."""

    status_code = 409
    default_detail = _("This meeting already has an active breakout session.")


class MediaServerError(exceptions.APIException):
    """A media server call failed; the detail never carries the upstream error."""

    status_code = 503
    default_detail = _("The media server could not be reached. Try again.")


async def _bounded(call):
    """Await one media server call under its own deadline."""
    async with asyncio.timeout(MEDIA_SERVER_TIMEOUT_SECONDS):
        return await call


async def _delete_rooms(lkapi, names):
    """Delete media server rooms, a room already gone counting as deleted."""
    results = await asyncio.gather(
        *(
            _bounded(lkapi.room.delete_room(DeleteRoomRequest(room=name)))
            for name in names
        ),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception) and not (
            isinstance(result, TwirpError) and result.code == "not_found"
        ):
            raise result


async def _create_rooms(lkapi, names):
    """Create media server rooms, deleting them all if any one fails."""
    results = await asyncio.gather(
        *(
            _bounded(
                lkapi.room.create_room(
                    CreateRoomRequest(name=name, empty_timeout=EMPTY_TIMEOUT_SECONDS)
                )
            )
            for name in names
        ),
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, Exception)]
    if errors:
        await _delete_rooms(lkapi, names)
        raise errors[0]


async def _write_metadata(lkapi, room_name, value):
    """Set the breakout key on a room's metadata, or remove it when value is None.

    Returns False when the room is not live on the media server.
    """
    response = await _bounded(
        lkapi.room.list_rooms(ListRoomsRequest(names=[room_name]))
    )
    if not response.rooms:
        return False
    metadata = json.loads(response.rooms[0].metadata or "{}")
    metadata.pop(METADATA_KEY, None)
    if value is not None:
        metadata[METADATA_KEY] = value
    await _bounded(
        lkapi.room.update_room_metadata(
            UpdateRoomMetadataRequest(room=room_name, metadata=json.dumps(metadata))
        )
    )
    return True


async def _close_media(lkapi, room_name, names):
    """Remove the signal before deleting the rooms, so nobody returning moves again."""
    is_live = await _write_metadata(lkapi, room_name, None)
    await _delete_rooms(lkapi, names)
    return is_live


def _run(step, *args):
    """Run one async step with its own client, turning any failure into a 503."""

    async def run():
        lkapi = utils.create_livekit_client()
        try:
            return await step(lkapi, *args)
        finally:
            await lkapi.aclose()

    try:
        return async_to_sync(run)()
    except Exception as error:
        logger.exception("Breakout media server step %s failed", step.__name__)
        raise MediaServerError() from error


def _discard_rooms(names):
    """Best-effort cleanup; a room left behind expires after EMPTY_TIMEOUT_SECONDS."""
    try:
        _run(_delete_rooms, names)
    except MediaServerError:
        pass


def open_session(room, user, rooms):
    """Create the media server rooms, then the rows, then signal the meeting."""
    active = models.BreakoutSessionStatusChoices.ACTIVE
    if room.breakout_sessions.filter(status=active).exists():
        raise SessionAlreadyActive()

    session_id = uuid4()
    names = [
        f"{models.BreakoutRoom.LIVEKIT_ROOM_PREFIX}{session_id}_{index}"
        for index in range(len(rooms))
    ]
    _run(_create_rooms, names)

    try:
        with transaction.atomic():
            session = models.BreakoutSession.objects.create(
                id=session_id, room=room, created_by=user
            )
            breakout_rooms = models.BreakoutRoom.objects.bulk_create(
                models.BreakoutRoom(
                    session=session, name=data["name"], livekit_room_name=name
                )
                for data, name in zip(rooms, names, strict=True)
            )
            models.BreakoutAssignment.objects.bulk_create(
                models.BreakoutAssignment(
                    session=session,
                    breakout_room=breakout_room,
                    identity=participant["identity"],
                    name=participant["name"],
                )
                for data, breakout_room in zip(rooms, breakout_rooms, strict=True)
                for participant in data["participants"]
            )
    except (IntegrityError, ValidationError) as error:
        _discard_rooms(names)
        raise SessionAlreadyActive() from error
    except Exception:
        _discard_rooms(names)
        raise

    signal = {"session_id": str(session.id), "status": active}
    try:
        is_live = _run(_write_metadata, str(room.id), signal)
    except MediaServerError:
        is_live = False
        # A write cut off by its deadline may still have landed; take it back.
        with contextlib.suppress(MediaServerError):
            _run(_write_metadata, str(room.id), None)
    if not is_live:
        session.delete()
        _discard_rooms(names)
        raise MediaServerError()
    return session


def close_session(session):
    """Remove the signal, delete the rooms, then mark the session closed.

    Closing a closed session does nothing, so a failed close is retried by closing again.
    """
    if session.status == models.BreakoutSessionStatusChoices.CLOSED:
        return session
    names = list(session.rooms.values_list("livekit_room_name", flat=True))
    is_live = _run(_close_media, str(session.room_id), names)

    session.status = models.BreakoutSessionStatusChoices.CLOSED
    session.closed_at = timezone.now()
    session.save(update_fields=["status", "closed_at", "updated_at"])
    if not is_live:
        # The meeting ended while the session was open, and room_finished kept these.
        LobbyService().clear_room_cache(session.room_id)
    return session


def join_pass(assignment, user):
    """A member's pass to the breakout room the participant is assigned to."""
    breakout_room = assignment.breakout_room
    configuration = assignment.session.room.configuration
    return {
        "url": settings.LIVEKIT_CONFIGURATION["url"],
        "room": breakout_room.livekit_room_name,
        "token": utils.generate_token(
            room=breakout_room.livekit_room_name,
            user=user,
            username=assignment.name or None,
            sources=configuration.get("can_publish_sources"),
            role=models.RoleChoices.MEMBER,
            participant_id=assignment.identity,
            ttl=JOIN_TOKEN_TTL,
        ),
    }
