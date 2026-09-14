"""Shared test fixtures for Device construction."""

from __future__ import annotations

from bleak.backends.device import BLEDevice

from pyfitdaysplus.device import Device

DEFAULT_ADDRESS = "78:66:A5:D3:47:1E"
DEFAULT_NAME = "MY_SCALE"


def ble_device(
    address: str = DEFAULT_ADDRESS,
    name: str | None = DEFAULT_NAME,
) -> BLEDevice:
    return BLEDevice(address, name, details={})


def scale() -> Device:
    return Device(address=DEFAULT_ADDRESS, name=DEFAULT_NAME)
