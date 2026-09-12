from unittest.mock import AsyncMock, MagicMock

import pytest

from icomon_kitchen.client import Client, KitchenScaleClient
from icomon_kitchen.config import COMM_PROTOCOL, Config
from icomon_kitchen.device import KitchenScaleDevice
from icomon_kitchen.models import ScannedDevice


@pytest.mark.asyncio
async def test_client_connect_and_disconnect() -> None:
    """The client delegates connect/disconnect to the adapter."""
    client = Client(Config(address="78:66:A5:D3:47:1E"))
    client._adapter.connect = AsyncMock()
    client._adapter.disconnect = AsyncMock()

    await client.connect()
    await client.disconnect()

    client._adapter.connect.assert_awaited_once()
    client._adapter.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_client_context_manager() -> None:
    """The async context manager connects on enter and disconnects on exit."""
    client = Client(Config(address="78:66:A5:D3:47:1E"))
    client._adapter.connect = AsyncMock()
    client._adapter.disconnect = AsyncMock()

    async with client:
        client._adapter.connect.assert_awaited_once()

    client._adapter.disconnect.assert_awaited_once()


def test_protocol_constant() -> None:
    """The generated protocol matches the template selection."""
    assert COMM_PROTOCOL == "ble"


def test_config_defaults() -> None:
    """Config can be constructed with defaults."""
    config = Config()
    assert config.ble_name == "MY_SCALE"
    assert config.device_type == 0x42


@pytest.mark.asyncio
async def test_scan_for_device_by_address() -> None:
    backend = MagicMock()
    client = KitchenScaleClient(backend=backend)
    client._adapter.create_transport = MagicMock(return_value=MagicMock())

    device = await client.scan_for_device(address="78:66:A5:D3:47:1E")
    assert isinstance(device, KitchenScaleDevice)
    assert device.info.address == "78:66:A5:D3:47:1E"


@pytest.mark.asyncio
async def test_scan_filters_by_name() -> None:
    class FakeBackend:
        async def discover(self, timeout: float) -> dict[str, tuple[object, object]]:
            device = MagicMock()
            device.address = "78:66:A5:D3:47:1E"
            device.name = "MY_SCALE"
            advertisement = MagicMock()
            advertisement.local_name = "MY_SCALE"
            advertisement.rssi = -55
            return {device.address: (device, advertisement)}

        def client(self, address: str) -> MagicMock:
            return MagicMock()

    client = KitchenScaleClient(backend=FakeBackend())
    matches = await client.scan(name="MY_SCALE", timeout=1.0)
    assert matches == [
        ScannedDevice(name="MY_SCALE", address="78:66:A5:D3:47:1E", rssi=-55)
    ]
