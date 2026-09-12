"""Awaitable accessor for ``await device.weight``."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .device import KitchenScaleDevice
    from .models import WeightReading


class WeightAccessor:
    """Support ``await device.weight`` without exposing raw protocol details."""

    __slots__ = ("_device",)

    def __init__(self, device: KitchenScaleDevice) -> None:
        self._device = device

    def __await__(self) -> Generator[Any, None, WeightReading]:
        return self._resolve().__await__()

    async def _resolve(self) -> WeightReading:
        if self._device._latest is not None:
            return self._device._latest
        return await self._device.read_weight()
