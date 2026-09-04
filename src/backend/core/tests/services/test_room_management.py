"""Tests for the RoomManagement service."""

import asyncio
import json
from threading import Event, Thread
from types import SimpleNamespace
from unittest import mock

import pytest
from livekit.api import TwirpError

from core.factories import RoomFactory
from core.models import RoomAccessLevel
from core.services.room_management import (
    RoomManagement,
    RoomManagementException,
    RoomNotFoundException,
)


@mock.patch("core.services.room_management.utils.create_livekit_client")
def test_delete_room_calls_livekit(mock_create_livekit_client):
    """DeleteRoom is forwarded to the LiveKit API."""
    mock_api = mock.MagicMock()
    mock_api.room.delete_room = mock.AsyncMock()
    mock_api.aclose = mock.AsyncMock()
    mock_create_livekit_client.return_value = mock_api

    RoomManagement.delete_room("room-abc")

    mock_api.room.delete_room.assert_awaited_once()
    request = mock_api.room.delete_room.await_args.args[0]
    assert request.room == "room-abc"
    mock_api.aclose.assert_awaited_once()


@mock.patch("core.services.room_management.utils.create_livekit_client")
def test_delete_room_raises_not_found(mock_create_livekit_client):
    """Missing rooms raise RoomNotFoundException."""
    mock_api = mock.MagicMock()
    mock_api.room.delete_room = mock.AsyncMock(
        side_effect=TwirpError("not_found", "room not found", status=404)
    )
    mock_api.aclose = mock.AsyncMock()
    mock_create_livekit_client.return_value = mock_api

    with pytest.raises(RoomNotFoundException):
        RoomManagement.delete_room("missing-room")

    mock_api.aclose.assert_awaited_once()


@mock.patch("core.services.room_management.utils.create_livekit_client")
def test_delete_room_raises_management_exception(mock_create_livekit_client):
    """Unexpected Twirp errors raise RoomManagementException."""
    mock_api = mock.MagicMock()
    mock_api.room.delete_room = mock.AsyncMock(
        side_effect=TwirpError("internal", "boom", status=500)
    )
    mock_api.aclose = mock.AsyncMock()
    mock_create_livekit_client.return_value = mock_api

    with pytest.raises(RoomManagementException):
        RoomManagement.delete_room("room-abc")

    mock_api.aclose.assert_awaited_once()


@mock.patch.object(RoomManagement, "update_metadata")
def test_sync_room_metadata_pushes_configuration_and_access_level(mock_update_metadata):
    """The room's configuration and access level are forwarded to LiveKit."""
    room = RoomFactory.build(
        access_level=RoomAccessLevel.RESTRICTED,
        configuration={"everyone_can_mute": True},
    )

    RoomManagement.sync_room_metadata(room)

    mock_update_metadata.assert_called_once_with(
        room_name=str(room.id),
        metadata={
            "configuration": {"everyone_can_mute": True},
            "access_level": RoomAccessLevel.RESTRICTED,
        },
    )


def test_concurrent_metadata_writers_preserve_breakout_state():
    """Recording updates cannot overwrite a concurrent breakout activation."""
    state = {"metadata": "{}", "reads": 0}
    first_read = Event()
    release_first = Event()
    second_started = Event()
    second_finished = Event()
    errors = []

    async def list_rooms(_request):
        metadata = state["metadata"]
        state["reads"] += 1
        if state["reads"] == 1:
            first_read.set()
            assert await asyncio.to_thread(release_first.wait, 5)
        return SimpleNamespace(rooms=[SimpleNamespace(metadata=metadata)])

    async def update_metadata(request):
        state["metadata"] = request.metadata

    def write(metadata, second=False):
        try:
            if second:
                second_started.set()
            RoomManagement.update_metadata("shared-room", metadata=metadata)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            errors.append(error)
        finally:
            if second:
                second_finished.set()

    def client():
        return SimpleNamespace(
            room=SimpleNamespace(
                list_rooms=list_rooms, update_room_metadata=update_metadata
            ),
            aclose=mock.AsyncMock(),
        )

    with mock.patch(
        "core.services.room_management.utils.create_livekit_client", side_effect=client
    ):
        first = Thread(target=write, args=({"breakout": {"revision": 1}},))
        second = Thread(target=write, args=({"recording_status": "active"}, True))
        first.start()
        try:
            assert first_read.wait(5)
            second.start()
            assert second_started.wait(5)
            second_finished.wait(0.5)
        finally:
            release_first.set()
            first.join(5)
            if second.ident is not None:
                second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert json.loads(state["metadata"]) == {
        "breakout": {"revision": 1},
        "recording_status": "active",
    }


def test_metadata_timeout_releases_lock_for_retry():
    """A stalled LiveKit read fails visibly without stranding the metadata lock."""

    async def stalled_read(_request):
        await asyncio.Event().wait()

    client = SimpleNamespace(
        room=SimpleNamespace(
            list_rooms=mock.AsyncMock(side_effect=stalled_read),
            update_room_metadata=mock.AsyncMock(),
        ),
        aclose=mock.AsyncMock(),
    )
    with (
        mock.patch(
            "core.services.room_management.utils.create_livekit_client",
            return_value=client,
        ),
        mock.patch(
            "core.services.room_management.utils.LIVEKIT_HTTP_TIMEOUT_SECONDS", 0.01
        ),
    ):
        with pytest.raises(RoomManagementException):
            RoomManagement.update_metadata("timeout-room", metadata={"breakout": {}})
        client.room.list_rooms.side_effect = None
        client.room.list_rooms.return_value = SimpleNamespace(
            rooms=[SimpleNamespace(metadata="{}")]
        )
        RoomManagement.update_metadata("timeout-room", metadata={"breakout": {}})
    assert client.aclose.await_count == 2
    client.room.update_room_metadata.assert_awaited_once()
