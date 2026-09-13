"""Injectable BLE backend abstraction."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    close_stale_connections,
    establish_connection,
    get_device,
)


@runtime_checkable
class BleBackend(Protocol):
    """Protocol implemented by the default bleak backend and test doubles."""

    async def discover(
        self,
        timeout: float,
    ) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
        """Scan for BLE devices keyed by address."""

    async def ble_device(self, address: str) -> BLEDevice | None:
        """Return a ``BLEDevice`` for ``address``, if the adapter knows it."""

    async def establish_connection(
        self,
        device: BLEDevice,
        name: str,
    ) -> BleakClient:
        """Connect to ``device`` with retry and return a connected client."""


class DefaultBleBackend:
    """Production backend using bleak plus bleak-retry-connector."""

    async def discover(
        self,
        timeout: float,
    ) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
        return await BleakScanner.discover(timeout=timeout, return_adv=True)

    async def ble_device(self, address: str) -> BLEDevice | None:
        device = await get_device(address)
        if device is not None:
            return device
        return await BleakScanner.find_device_by_address(address)

    async def establish_connection(
        self,
        device: BLEDevice,
        name: str,
    ) -> BleakClient:
        await close_stale_connections(device)
        return await establish_connection(
            BleakClientWithServiceCache,
            device,
            name,
            use_services_cache=True,
        )
