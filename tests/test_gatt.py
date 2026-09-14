"""Tests for BLE GATT characteristic discovery."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from pyfitdaysplus.ble.gatt import discover_scale_characteristics
from pyfitdaysplus.device import Device
from pyfitdaysplus.exceptions import ProtocolError
from pyfitdaysplus.protocol.constants import (
    CHAR_FILE_WRITE_UUID,
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    SERVICE_UUID,
)
from tests.factories import ble_device


class FakeChar:
    def __init__(self, uuid: str, properties: list[str] | None = None) -> None:
        self.uuid = uuid
        self.properties = list(properties or [])


class FakeService:
    def __init__(self, uuid: str, chars: list[FakeChar]) -> None:
        self.uuid = uuid
        self.characteristics = chars

    def get_characteristic(self, uuid: str) -> FakeChar | None:
        for char in self.characteristics:
            if char.uuid == str(uuid):
                return char
        return None


class FakeServices:
    def __init__(self, services: list[FakeService]) -> None:
        self._services = services
        self.characteristics = dict(
            enumerate(
                (char for service in services for char in service.characteristics),
                start=1,
            )
        )

    def __iter__(self):
        """Yield GATT services in discovery order."""
        return iter(self._services)

    def get_service(self, specifier: str | UUID) -> FakeService | None:
        for service in self._services:
            if service.uuid == str(specifier):
                return service
        return None


class FakeClient:
    def __init__(self, services: FakeServices) -> None:
        self.services = services
        self.is_connected = True
        self.notify_started = False
        self.writes: list[tuple[str, bytes, bool]] = []

    async def disconnect(self) -> None:
        self.is_connected = False

    async def start_notify(self, _uuid: str, _callback: Any) -> None:
        self.notify_started = True

    async def stop_notify(self, _uuid: str) -> None:
        self.notify_started = False

    async def write_gatt_char(
        self,
        uuid: str,
        data: bytes,
        response: bool = True,
    ) -> None:
        self.writes.append((uuid, bytes(data), response))


def _service(*char_uuids: str, service_uuid: str | None = None) -> FakeServices:
    chars = [FakeChar(uuid) for uuid in char_uuids]
    return FakeServices([FakeService(service_uuid or str(SERVICE_UUID), chars)])


async def _connect(client: FakeClient) -> Device:
    device = Device(ble_device(), fun_info_timeout=0.01)
    with patch(
        "pyfitdaysplus.device.establish_connection",
        AsyncMock(return_value=client),
    ):
        await device.connect()
    return device


def test_discover_succeeds_without_optional_ffb4() -> None:
    chars = discover_scale_characteristics(
        _service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID))
    )
    assert chars.file_write_uuid is None


def test_discover_records_ffb4_when_present() -> None:
    chars = discover_scale_characteristics(
        _service(
            str(CHAR_WRITE_UUID),
            str(CHAR_NOTIFY_UUID),
            str(CHAR_FILE_WRITE_UUID),
        )
    )
    assert chars.file_write_uuid == str(CHAR_FILE_WRITE_UUID)


def test_discover_matches_short_uuids() -> None:
    chars = discover_scale_characteristics(
        _service("ffb1", "ffb2", service_uuid="ffb0")
    )
    assert chars.write_uuid == "ffb1"
    assert chars.notify_uuid == "ffb2"


def test_discover_fails_when_write_characteristic_missing() -> None:
    with pytest.raises(ProtocolError, match="missing FFB1"):
        discover_scale_characteristics(_service(str(CHAR_NOTIFY_UUID)))


def test_discover_fails_when_service_missing() -> None:
    with pytest.raises(ProtocolError, match=r"service .* not found"):
        discover_scale_characteristics(FakeServices([FakeService("180a", [])]))


@pytest.mark.asyncio
async def test_write_file_requires_ffb4() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = await _connect(client)

    with pytest.raises(ProtocolError, match="FFB4"):
        await device._write_file(b"icon")

    await device.disconnect()


@pytest.mark.asyncio
async def test_write_file_uses_discovered_ffb4() -> None:
    client = FakeClient(
        _service(
            str(CHAR_WRITE_UUID),
            str(CHAR_NOTIFY_UUID),
            str(CHAR_FILE_WRITE_UUID),
        )
    )
    device = await _connect(client)
    await device._write_file(b"icon")

    assert (str(CHAR_FILE_WRITE_UUID), b"icon", False) in client.writes
    await device.disconnect()


@pytest.mark.asyncio
async def test_write_command_prefers_write_without_response() -> None:
    client = FakeClient(
        FakeServices(
            [
                FakeService(
                    str(SERVICE_UUID),
                    [
                        FakeChar(
                            str(CHAR_WRITE_UUID),
                            ["write", "write-without-response"],
                        ),
                        FakeChar(str(CHAR_NOTIFY_UUID), ["notify"]),
                    ],
                )
            ]
        )
    )
    device = await _connect(client)
    await device._write_command(b"\xac\x42")

    assert (str(CHAR_WRITE_UUID), b"\xac\x42", False) in client.writes
    await device.disconnect()


@pytest.mark.asyncio
async def test_write_command_uses_response_when_only_write() -> None:
    client = FakeClient(
        FakeServices(
            [
                FakeService(
                    str(SERVICE_UUID),
                    [
                        FakeChar(str(CHAR_WRITE_UUID), ["write"]),
                        FakeChar(str(CHAR_NOTIFY_UUID), ["notify"]),
                    ],
                )
            ]
        )
    )
    device = await _connect(client)
    await device._write_command(b"\xac\x42")

    assert (str(CHAR_WRITE_UUID), b"\xac\x42", True) in client.writes
    await device.disconnect()


@pytest.mark.asyncio
async def test_connect_subscribes_and_disconnect_unsubscribes() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = await _connect(client)

    assert device.connected
    assert client.notify_started is True

    await device.disconnect()
    assert client.notify_started is False
    assert client.is_connected is False
