from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak_retry_connector import BleakClientWithServiceCache

from pyfitdaysplus.config import COMM_PROTOCOL
from pyfitdaysplus.device import Device
from pyfitdaysplus.events import Event
from pyfitdaysplus.exceptions import NotConnectedError
from tests.factories import ble_device, scale
from tests.test_gatt import (
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    FakeClient,
    _connect,
    _service,
)


def test_protocol_constant() -> None:
    """The generated protocol matches the template selection."""
    assert COMM_PROTOCOL == "ble"


def test_device_uses_ble_device_identity() -> None:
    device_info = ble_device()
    device = Device(device_info)
    assert isinstance(device, Device)
    assert device.address == device_info.address
    assert device.name == "MY_SCALE"
    assert device.info.device_type == 0x42
    assert device.ble_device is device_info


def test_device_init_without_ble_device() -> None:
    device = Device(address="78:66:A5:D3:47:1E", name="MY_SCALE")
    assert device.ble_device is None
    assert device.address == "78:66:A5:D3:47:1E"
    assert device.name == "MY_SCALE"


def test_device_init_requires_address_or_ble_device() -> None:
    with pytest.raises(ValueError, match="BLEDevice or an address"):
        Device()


@pytest.mark.asyncio
async def test_connect_without_ble_device_raises() -> None:
    device = Device(address="78:66:A5:D3:47:1E")
    with pytest.raises(NotConnectedError, match="no BLEDevice"):
        await device.connect()


@pytest.mark.asyncio
async def test_connect_after_attaching_ble_device() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    ble = ble_device()
    device = Device(address=ble.address, fun_info_timeout=0.01)
    device.set_ble_device_and_advertisement_data(ble)
    with patch(
        "pyfitdaysplus.device.establish_connection",
        AsyncMock(return_value=client),
    ) as connect:
        await device.connect()

    connect.assert_awaited_once()
    awaited = connect.await_args
    assert awaited is not None
    assert awaited.args == (BleakClientWithServiceCache, ble, "MY_SCALE")
    assert device.connected
    await device.disconnect()


def test_set_ble_device_updates_path() -> None:
    device = scale()
    updated = ble_device("AA:BB:CC:DD:EE:FF", "OTHER")
    advertisement = MagicMock()
    device.set_ble_device_and_advertisement_data(updated, advertisement)
    assert device.address == "AA:BB:CC:DD:EE:FF"
    assert device.name == "OTHER"
    assert device.ble_device is updated
    assert device.advertisement_data is advertisement


@pytest.mark.asyncio
async def test_connect_uses_establish_connection() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    ble = ble_device()
    device = Device(ble, fun_info_timeout=0.01)
    with patch(
        "pyfitdaysplus.device.establish_connection",
        AsyncMock(return_value=client),
    ) as connect:
        await device.connect()

    connect.assert_awaited_once()
    awaited = connect.await_args
    assert awaited is not None
    args, kwargs = awaited
    assert args == (BleakClientWithServiceCache, ble, "MY_SCALE")
    assert kwargs["use_services_cache"] is True
    assert kwargs["disconnected_callback"] == device._on_disconnect
    assert device.connected
    await device.disconnect()
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_connect_and_disconnect_emit_lifecycle_events() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = Device(ble_device(), fun_info_timeout=0.01)
    lifecycle: list[str] = []
    device.subscribe([Event.CONNECT, Event.DISCONNECT], lifecycle.append)
    with patch(
        "pyfitdaysplus.device.establish_connection",
        AsyncMock(return_value=client),
    ):
        await device.connect()
    assert lifecycle == [device.address]
    await device.disconnect()
    assert lifecycle == [device.address, device.address]
    assert device.connected is False


@pytest.mark.asyncio
async def test_unexpected_disconnect_resets_session_once() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = await _connect(client)
    dropped: list[str] = []
    device.subscribe(Event.DISCONNECT, dropped.append)
    device._fun_info_event.set()
    device._on_device_confirm_held = True

    device._on_disconnect(client)

    assert device.connected is False
    assert device.capabilities is None
    assert device._chars is None
    assert not device._fun_info_event.is_set()
    assert device._on_device_confirm_held is False
    assert dropped == [device.address]

    await device.disconnect()
    assert dropped == [device.address]
