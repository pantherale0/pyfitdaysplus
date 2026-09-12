"""Library-specific exceptions."""

from __future__ import annotations


class IcomonKitchenError(Exception):
    """Base error for this library."""


class DeviceNotFoundError(IcomonKitchenError):
    """No matching BLE device was found during scanning."""


class NotConnectedError(IcomonKitchenError):
    """The scale is not connected."""


class ProtocolError(IcomonKitchenError):
    """A frame could not be encoded or decoded."""


class UnsupportedProtocolError(IcomonKitchenError):
    """The device uses a protocol variant that is not implemented yet."""
