"""BLE GATT transport for ICOMON kitchen scales."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from uuid import UUID

from bleak.backends.characteristic import BleakGATTCharacteristic

from ..exceptions import NotConnectedError, ProtocolError
from ..protocol.constants import (
    CHAR_FILE_WRITE_UUID,
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    SERVICE_UUID,
)
from ..protocol.framing import encode_file_frame
from .backend import BleBackend, DefaultBleBackend

if TYPE_CHECKING:
    from bleak import BleakClient


class BleTransport:
    """Write commands and receive notifications on the ICOMON GATT service."""

    def __init__(
        self,
        address: str,
        *,
        backend: BleBackend | None = None,
        service_uuid: UUID = SERVICE_UUID,
        write_uuid: UUID = CHAR_WRITE_UUID,
        notify_uuid: UUID = CHAR_NOTIFY_UUID,
        file_write_uuid: UUID = CHAR_FILE_WRITE_UUID,
    ) -> None:
        self.address = address
        self._backend = backend or DefaultBleBackend()
        self._service_uuid = service_uuid
        self._write_uuid = write_uuid
        self._notify_uuid = notify_uuid
        self._file_write_uuid = file_write_uuid
        self._client: BleakClient | None = None
        self._notify_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._write_uuid_str = str(write_uuid)
        self._notify_uuid_str = str(notify_uuid)
        self._file_write_uuid_str = str(file_write_uuid)

    @property
    def connected(self) -> bool:
        """Return whether the BLE link is active."""
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        """Connect and subscribe to scale notifications."""
        if self.connected:
            return
        client = self._backend.client(self.address)
        await client.connect()
        self._client = client
        await self._discover_characteristics()
        await client.start_notify(self._notify_uuid_str, self._on_notify)

    async def disconnect(self) -> None:
        """Unsubscribe and close the BLE connection."""
        if self._client is None:
            return
        await self._client.stop_notify(self._notify_uuid_str)
        await self._client.disconnect()
        self._client = None

    async def write_command(self, frame: bytes) -> None:
        """Send a framed command on FFB1."""
        client = self._require_client()
        await client.write_gatt_char(self._write_uuid_str, frame, response=True)

    async def write_file(self, data: bytes) -> None:
        """Send a raw file chunk on FFB4."""
        client = self._require_client()
        await client.write_gatt_char(
            self._file_write_uuid_str,
            encode_file_frame(data),
            response=True,
        )

    async def notifications(self) -> AsyncIterator[bytes]:
        """Yield raw notification payloads from FFB2."""
        while self.connected:
            yield await self._notify_queue.get()

    def _on_notify(
        self,
        _characteristic: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        self._notify_queue.put_nowait(bytes(data))

    async def _discover_characteristics(self) -> None:
        client = self._require_client()
        service = client.services.get_service(str(self._service_uuid))
        if service is None:
            msg = f"service {self._service_uuid} not found"
            raise ProtocolError(msg)

        write = service.get_characteristic(str(self._write_uuid))
        notify = service.get_characteristic(str(self._notify_uuid))
        file_write = service.get_characteristic(str(self._file_write_uuid))
        if write is None or notify is None or file_write is None:
            msg = "required FFB0 service characteristics not found"
            raise ProtocolError(msg)

    def _require_client(self) -> BleakClient:
        if self._client is None or not self._client.is_connected:
            raise NotConnectedError("call connect() before using the transport")
        return self._client
