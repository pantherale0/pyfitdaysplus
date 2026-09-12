"""Accessors for cached and awaitable weight readings."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .device import KitchenScaleDevice
    from .models import WeightReading


class WeightAccessor:
    """
    Support ``await device.weight`` without exposing raw protocol details.

    Returns the cached reading when available, otherwise waits for the next
    live ``0xA6`` notification.
    """

    __slots__ = ("_device",)

    def __init__(self, device: KitchenScaleDevice) -> None:
        self._device = device

    def __await__(self) -> Generator[Any, None, WeightReading]:
        return self._resolve().__await__()

    async def _resolve(self) -> WeightReading:
        cached = self._device.latest_weight
        if cached is not None:
            return cached
        return await self._device.read_weight()


class CachedWeightAccessor:
    """Sync access to the cached weight reading on :class:`KitchenScaleDevice`."""

    __slots__ = ("_device",)

    def __init__(self, device: KitchenScaleDevice) -> None:
        self._device = device

    @property
    def reading(self) -> WeightReading | None:
        """Latest cached :class:`WeightReading`, or ``None`` before the first notify."""
        return self._device.latest_weight

    @property
    def grams(self) -> float | None:
        """Latest weight in grams, or ``None`` when no reading is cached yet."""
        reading = self.reading
        return None if reading is None else reading.grams

    @property
    def milligrams(self) -> int | None:
        """Latest weight in milligrams, or ``None`` when no reading is cached yet."""
        reading = self.reading
        return None if reading is None else reading.milligrams

    @property
    def stable(self) -> bool | None:
        """Stability flag from the latest cached reading, if any."""
        reading = self.reading
        return None if reading is None else reading.stable
