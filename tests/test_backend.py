from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak_retry_connector import BleakClientWithServiceCache

from pyfitdaysplus.ble.backend import DefaultBleBackend

ADDRESS = "78:66:A5:D3:47:1E"


def _ble_device() -> MagicMock:
    device = MagicMock()
    device.address = ADDRESS
    device.name = "MY_SCALE"
    return device


@pytest.mark.asyncio
async def test_ble_device_prefers_bluez_lookup() -> None:
    device = _ble_device()
    backend = DefaultBleBackend()
    with (
        patch(
            "pyfitdaysplus.ble.backend.get_device",
            AsyncMock(return_value=device),
        ) as get_device,
        patch(
            "pyfitdaysplus.ble.backend.BleakScanner.find_device_by_address",
            AsyncMock(),
        ) as find,
    ):
        assert await backend.ble_device(ADDRESS) is device

    get_device.assert_awaited_once_with(ADDRESS)
    find.assert_not_awaited()


@pytest.mark.asyncio
async def test_ble_device_falls_back_to_scanner() -> None:
    device = _ble_device()
    backend = DefaultBleBackend()
    with (
        patch("pyfitdaysplus.ble.backend.get_device", AsyncMock(return_value=None)),
        patch(
            "pyfitdaysplus.ble.backend.BleakScanner.find_device_by_address",
            AsyncMock(return_value=device),
        ) as find,
    ):
        assert await backend.ble_device(ADDRESS) is device

    find.assert_awaited_once_with(ADDRESS)


@pytest.mark.asyncio
async def test_establish_connection_uses_retry_connector() -> None:
    device = _ble_device()
    client = MagicMock()
    backend = DefaultBleBackend()
    with (
        patch(
            "pyfitdaysplus.ble.backend.close_stale_connections",
            AsyncMock(),
        ) as close,
        patch(
            "pyfitdaysplus.ble.backend.establish_connection",
            AsyncMock(return_value=client),
        ) as connect,
    ):
        result = await backend.establish_connection(device, "MY_SCALE")

    assert result is client
    close.assert_awaited_once_with(device)
    connect.assert_awaited_once()
    awaited = connect.await_args
    assert awaited is not None
    args, kwargs = awaited
    assert args == (BleakClientWithServiceCache, device, "MY_SCALE")
    assert kwargs["use_services_cache"] is True
