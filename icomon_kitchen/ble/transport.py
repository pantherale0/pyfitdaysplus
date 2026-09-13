"""BLE GATT transport for ICOMON kitchen scales."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING
from uuid import UUID

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.service import BleakGATTService, BleakGATTServiceCollection
from bleak.uuids import normalize_uuid_str

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

_LOGGER = logging.getLogger(__name__)


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
        self._notify_started = False
        self._write_uuid_str = str(write_uuid)
        self._notify_uuid_str = str(notify_uuid)
        self._file_write_uuid_str: str | None = str(file_write_uuid)
        self._write_with_response = False
        self._file_write_with_response = False

    @property
    def connected(self) -> bool:
        """Return whether the BLE link is active."""
        return self._client is not None and self._client.is_connected

    @property
    def att_mtu(self) -> int:
        """Negotiated ATT MTU, or 23 when the backend has not reported one."""
        client = self._client
        if client is None:
            return 23
        size = getattr(client, "mtu_size", None)
        if isinstance(size, int) and size >= 23:
            return size
        return 23

    async def connect(self) -> None:
        """Connect and subscribe to scale notifications."""
        if self.connected:
            return
        client = self._backend.client(self.address)
        try:
            _LOGGER.info("connecting to %s", self.address)
            await client.connect()
            self._client = client
            await self._discover_characteristics()
            _LOGGER.info("enabling notifications on %s", self._notify_uuid_str)
            await client.start_notify(self._notify_uuid_str, self._on_notify)
            self._notify_started = True
            await self._refresh_att_mtu(client)
            _LOGGER.info("GATT session ready on %s", self.address)
        except BaseException:
            _LOGGER.debug("connect failed for %s", self.address, exc_info=True)
            await self.disconnect()
            raise

    def has_service(self, uuid: UUID) -> bool:
        """Return whether a GATT service UUID is present on the connected device."""
        return self._gatt_has_uuid(uuid, chars=False)

    def has_characteristic(self, uuid: UUID) -> bool:
        """Return whether a GATT characteristic UUID is present."""
        return self._gatt_has_uuid(uuid, chars=True)

    def _gatt_has_uuid(self, uuid: UUID, *, chars: bool) -> bool:
        client = self._client
        if client is None:
            return False
        key = _uuid_key(uuid)
        for service in client.services:
            if not chars and _uuid_key(service.uuid) == key:
                return True
            if chars:
                for characteristic in service.characteristics:
                    if _uuid_key(characteristic.uuid) == key:
                        return True
        return False

    async def disconnect(self) -> None:
        """Unsubscribe and close the BLE connection."""
        client = self._client
        notify_started = self._notify_started
        self._client = None
        self._notify_started = False
        if client is None:
            return
        _LOGGER.info("disconnecting from %s", self.address)
        try:
            if notify_started and client.is_connected:
                await client.stop_notify(self._notify_uuid_str)
        finally:
            if client.is_connected:
                await client.disconnect()

    async def write_command(self, frame: bytes) -> None:
        """Send a framed command on FFB1."""
        client = self._require_client()
        _LOGGER.debug(
            "write FFB1 response=%s payload=%s",
            self._write_with_response,
            frame.hex(),
        )
        await client.write_gatt_char(
            self._write_uuid_str,
            frame,
            response=self._write_with_response,
        )

    async def write_file(self, data: bytes) -> None:
        """Send a raw file chunk on FFB4."""
        if self._file_write_uuid_str is None:
            msg = "FFB4 file-write characteristic is not present on this scale"
            raise ProtocolError(msg)
        client = self._require_client()
        payload = encode_file_frame(data)
        _LOGGER.debug(
            "write FFB4 response=%s payload=%s",
            self._file_write_with_response,
            payload.hex(),
        )
        await client.write_gatt_char(
            self._file_write_uuid_str,
            payload,
            response=self._file_write_with_response,
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
        payload = bytes(data)
        _LOGGER.debug("notify %s: %s", _characteristic.uuid, payload.hex())
        self._notify_queue.put_nowait(payload)

    async def _discover_characteristics(self) -> None:
        client = self._require_client()
        services = client.services
        _log_gatt_table(services)
        service = _find_service(services, self._service_uuid)
        if service is None:
            found = _format_uuids(svc.uuid for svc in services) or "none"
            msg = f"service {self._service_uuid} not found (found: {found})"
            raise ProtocolError(msg)

        write = _find_characteristic(service, services, self._write_uuid)
        notify = _find_characteristic(service, services, self._notify_uuid)
        file_write = _find_characteristic(service, services, self._file_write_uuid)
        if write is None or notify is None:
            missing: list[str] = []
            if write is None:
                missing.append(f"FFB1 ({self._write_uuid})")
            if notify is None:
                missing.append(f"FFB2 ({self._notify_uuid})")
            found = (
                _format_uuids(
                    char.uuid for char in _iter_characteristics(service, services)
                )
                or "none"
            )
            msg = (
                "required FFB0 service characteristics not found: "
                f"missing {', '.join(missing)} (found: {found})"
            )
            raise ProtocolError(msg)

        self._write_uuid_str = write.uuid
        self._notify_uuid_str = notify.uuid
        self._write_with_response = _att_write_response(write)
        if file_write is None:
            self._file_write_uuid_str = None
            self._file_write_with_response = False
            _LOGGER.info(
                "FFB0 write=%s notify=%s file=absent write_with_response=%s",
                write.uuid,
                notify.uuid,
                self._write_with_response,
            )
            return

        self._file_write_uuid_str = file_write.uuid
        self._file_write_with_response = _att_write_response(file_write)
        _LOGGER.info(
            "FFB0 write=%s notify=%s file=%s write_with_response=%s",
            write.uuid,
            notify.uuid,
            file_write.uuid,
            self._write_with_response,
        )

    async def _refresh_att_mtu(self, client: BleakClient) -> None:
        """Copy BlueZ's negotiated GATT MTU onto the Bleak client when possible."""
        backend = getattr(client, "_backend", None)
        if backend is None:
            return
        mtu = await _bluez_gatt_mtu(backend)
        if mtu is None or mtu < 23:
            return
        backend._mtu_size = mtu
        _LOGGER.info("BlueZ GATT MTU=%s", mtu)

    def _require_client(self) -> BleakClient:
        if self._client is None or not self._client.is_connected:
            raise NotConnectedError("call connect() before using the transport")
        return self._client


def _uuid_equal(left: str | UUID, right: str | UUID) -> bool:
    """Return whether two BLE UUIDs match after 16-bit/128-bit normalization."""
    return normalize_uuid_str(str(left)) == normalize_uuid_str(str(right))


def _find_service(
    services: BleakGATTServiceCollection,
    uuid: UUID,
) -> BleakGATTService | None:
    for service in services:
        if _uuid_equal(service.uuid, uuid):
            return service
    return None


def _find_characteristic(
    service: BleakGATTService,
    services: BleakGATTServiceCollection,
    uuid: UUID,
) -> BleakGATTCharacteristic | None:
    for characteristic in _iter_characteristics(service, services):
        if _uuid_equal(characteristic.uuid, uuid):
            return characteristic
    return None


def _iter_characteristics(
    service: BleakGATTService,
    services: BleakGATTServiceCollection,
) -> list[BleakGATTCharacteristic]:
    found: list[BleakGATTCharacteristic] = list(service.characteristics)
    seen = {_uuid_key(char.uuid) for char in found}
    for characteristic in services.characteristics.values():
        key = _uuid_key(characteristic.uuid)
        if key in seen:
            continue
        seen.add(key)
        found.append(characteristic)
    return found


def _uuid_key(uuid: str | UUID) -> str:
    return normalize_uuid_str(str(uuid))


def _format_uuids(uuids: Iterable[str]) -> str:
    return ", ".join(sorted(set(uuids)))


def _att_write_response(characteristic: BleakGATTCharacteristic) -> bool:
    """Prefer write-without-response when the characteristic supports it."""
    properties = {prop.lower() for prop in characteristic.properties}
    if "write-without-response" in properties:
        return False
    return "write" in properties


def _log_gatt_table(services: BleakGATTServiceCollection) -> None:
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return
    for service in services:
        _LOGGER.debug("GATT service %s", service.uuid)
        for characteristic in service.characteristics:
            properties = ",".join(characteristic.properties) or "none"
            _LOGGER.debug(
                "  char %s properties=%s",
                characteristic.uuid,
                properties,
            )


async def _bluez_gatt_mtu(backend: object) -> int | None:
    """Return BlueZ's per-characteristic MTU property when the backend exposes it."""
    try:
        from bleak.backends.bluezdbus import defs
        from bleak.backends.bluezdbus.manager import get_global_bluez_manager
    except ImportError:
        return None
    device_path = getattr(backend, "_device_path", None)
    if not isinstance(device_path, str) or not device_path:
        return None
    try:
        manager = await get_global_bluez_manager()
        properties = getattr(manager, "_properties", {})
        for path, ifaces in properties.items():
            if not str(path).startswith(device_path):
                continue
            gatt = ifaces.get(defs.GATT_CHARACTERISTIC_INTERFACE)
            if not isinstance(gatt, dict):
                continue
            mtu = gatt.get("MTU")
            if isinstance(mtu, int) and mtu >= 23:
                return mtu
    except Exception:
        _LOGGER.debug("BlueZ MTU lookup failed", exc_info=True)
    return None
