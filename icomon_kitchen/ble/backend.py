"""Injectable BLE backend abstraction."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


@runtime_checkable
class BleBackend(Protocol):
    """Protocol implemented by the default bleak backend and test doubles."""

    async def discover(
        self,
        timeout: float,
    ) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
        """Scan for BLE devices keyed by address."""

    def client(self, address: str) -> BleakClient:
        """Return a client for ``address``."""


class DefaultBleBackend:
    """Production backend that wraps bleak directly."""

    async def discover(
        self,
        timeout: float,
    ) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
        return await BleakScanner.discover(timeout=timeout, return_adv=True)

    def client(self, address: str) -> BleakClient:
        return BleakClient(address)
