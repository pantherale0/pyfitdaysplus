"""Library-specific exceptions."""

from __future__ import annotations


class IcomonKitchenError(Exception):
    """Base error for this library."""


class NotConnectedError(IcomonKitchenError):
    """The scale is not connected."""


class ProtocolError(IcomonKitchenError):
    """A frame could not be encoded or decoded."""
