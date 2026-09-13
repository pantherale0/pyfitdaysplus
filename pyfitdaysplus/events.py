"""Single-registry event dispatch for device notifications."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

Unsubscribe = Callable[[], None]
Handler = Callable[..., None]


class Event(str, Enum):
    """Notification kinds that :class:`~pyfitdaysplus.device.Device` can emit."""

    WEIGHT = "weight"
    TICK = "tick"
    FOOD = "food"
    CAPABILITIES = "capabilities"
    BATTERY = "battery"


class EventRegistry:
    """Map each :class:`Event` to zero or more handlers; emit on the event loop."""

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: dict[Event, list[Handler]] = {event: [] for event in Event}

    def subscribe(self, event: Event, handler: Handler) -> Unsubscribe:
        """Register ``handler`` for ``event`` and return a callable that removes it."""
        listeners = self._listeners[event]
        listeners.append(handler)

        def unsubscribe() -> None:
            try:
                listeners.remove(handler)
            except ValueError:
                pass

        return unsubscribe

    def emit(self, event: Event, value: object) -> None:
        """Invoke all handlers registered for ``event``."""
        for handler in list(self._listeners[event]):
            handler(value)
