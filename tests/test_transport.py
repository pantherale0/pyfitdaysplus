"""Tests for BLE GATT characteristic discovery."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import pytest

from icomon_kitchen.ble.backend import BleBackend
from icomon_kitchen.ble.transport import BleTransport
from icomon_kitchen.exceptions import ProtocolError
from icomon_kitchen.protocol.constants import (
    CHAR_FILE_WRITE_UUID,
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    SERVICE_UUID,
)


class FakeChar:
    def __init__(self, uuid: str, properties: list[str] | None = None) -> None:
        self.uuid = uuid
        self.properties = list(properties or [])


class FakeService:
    def __init__(self, uuid: str, chars: list[FakeChar]) -> None:
        self.uuid = uuid
        self.characteristics = chars

    def get_characteristic(self, uuid: str) -> FakeChar | None:
        # Mimic older Bleak matching that fails on short vs long UUID forms.
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
        self.is_connected = False
        self.notify_started = False
        self.writes: list[tuple[str, bytes, bool]] = []

    async def connect(self) -> None:
        self.is_connected = True

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


class FakeBackend:
    def __init__(self, client: FakeClient) -> None:
        self._client = client

    async def discover(self, timeout: float) -> dict[str, tuple[object, object]]:
        return {}

    def client(self, _address: str) -> FakeClient:
        return self._client


def _service(*char_uuids: str, service_uuid: str | None = None) -> FakeServices:
    chars = [FakeChar(uuid) for uuid in char_uuids]
    return FakeServices([FakeService(service_uuid or str(SERVICE_UUID), chars)])


def _transport(client: FakeClient) -> BleTransport:
    return BleTransport(
        "78:66:A5:D3:47:1E",
        backend=cast(BleBackend, FakeBackend(client)),
    )


@pytest.mark.asyncio
async def test_connect_succeeds_without_optional_ffb4() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    transport = _transport(client)

    await transport.connect()

    assert transport.connected
    assert client.notify_started is True
    assert transport._file_write_uuid_str is None

    await transport.disconnect()
    assert client.is_connected is False
    assert client.notify_started is False


@pytest.mark.asyncio
async def test_connect_records_ffb4_when_present() -> None:
    client = FakeClient(
        _service(
            str(CHAR_WRITE_UUID),
            str(CHAR_NOTIFY_UUID),
            str(CHAR_FILE_WRITE_UUID),
        )
    )
    transport = _transport(client)

    await transport.connect()

    assert transport._file_write_uuid_str == str(CHAR_FILE_WRITE_UUID)
    await transport.disconnect()


@pytest.mark.asyncio
async def test_connect_matches_short_uuids() -> None:
    client = FakeClient(_service("ffb1", "ffb2", service_uuid="ffb0"))
    transport = _transport(client)

    await transport.connect()

    assert transport._write_uuid_str == "ffb1"
    assert transport._notify_uuid_str == "ffb2"
    await transport.disconnect()


@pytest.mark.asyncio
async def test_connect_fails_when_write_characteristic_missing() -> None:
    client = FakeClient(_service(str(CHAR_NOTIFY_UUID)))
    transport = _transport(client)

    with pytest.raises(ProtocolError, match="missing FFB1"):
        await transport.connect()

    assert client.is_connected is False
    assert transport.connected is False


@pytest.mark.asyncio
async def test_connect_fails_when_service_missing() -> None:
    client = FakeClient(FakeServices([FakeService("180a", [])]))
    transport = _transport(client)

    with pytest.raises(ProtocolError, match=r"service .* not found"):
        await transport.connect()

    assert client.is_connected is False


@pytest.mark.asyncio
async def test_write_file_requires_ffb4() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    transport = _transport(client)
    await transport.connect()

    with pytest.raises(ProtocolError, match="FFB4"):
        await transport.write_file(b"icon")

    await transport.disconnect()


@pytest.mark.asyncio
async def test_write_file_uses_discovered_ffb4() -> None:
    client = FakeClient(
        _service(
            str(CHAR_WRITE_UUID),
            str(CHAR_NOTIFY_UUID),
            str(CHAR_FILE_WRITE_UUID),
        )
    )
    transport = _transport(client)
    await transport.connect()
    await transport.write_file(b"icon")

    assert client.writes == [(str(CHAR_FILE_WRITE_UUID), b"icon", False)]
    await transport.disconnect()


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
    transport = _transport(client)
    await transport.connect()
    await transport.write_command(b"\xac\x42")

    assert client.writes == [(str(CHAR_WRITE_UUID), b"\xac\x42", False)]
    await transport.disconnect()


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
    transport = _transport(client)
    await transport.connect()
    await transport.write_command(b"\xac\x42")

    assert client.writes == [(str(CHAR_WRITE_UUID), b"\xac\x42", True)]
    await transport.disconnect()
