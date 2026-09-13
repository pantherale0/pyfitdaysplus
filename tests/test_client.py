from unittest.mock import MagicMock

import pytest

from pyfitdaysplus.client import Client, KitchenScaleClient
from pyfitdaysplus.config import COMM_PROTOCOL, Config
from pyfitdaysplus.device import Device
from pyfitdaysplus.models import ScannedDevice


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
    device = await client.scan_for_device(address="78:66:A5:D3:47:1E")
    assert isinstance(device, Device)
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

    client = KitchenScaleClient(backend=FakeBackend())
    matches = await client.scan(name="MY_SCALE", timeout=1.0)
    assert matches == [
        ScannedDevice(name="MY_SCALE", address="78:66:A5:D3:47:1E", rssi=-55)
    ]


@pytest.mark.asyncio
async def test_client_alias_is_kitchen_scale_client() -> None:
    assert Client is KitchenScaleClient
