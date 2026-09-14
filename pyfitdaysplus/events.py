"""Single-registry event dispatch for device notifications."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

Unsubscribe = Callable[[], None]
Handler = Callable[..., None]


class Event(StrEnum):
    """Notification kinds that :class:`~pyfitdaysplus.device.Device` can emit."""

    WEIGHT = "weight"
    ON_DEVICE_CONFIRM = "on_device_confirm"
    HISTORY = "history"
    FOOD_WEIGH = "food_weigh"
    FOOD = "food"
    CAPABILITIES = "capabilities"
    BATTERY = "battery"
    CONNECT = "connect"
    DISCONNECT = "disconnect"


class EventRegistry:
    """Map each :class:`Event` to zero or more handlers; emit on the event loop."""

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: dict[Event, list[Handler]] = {event: [] for event in Event}

    def subscribe(self, event: Event | list[Event], handler: Handler) -> Unsubscribe:
        """Register ``handler`` for ``event`` and return a callable that removes it."""
        if isinstance(event, list):
            unsubscribes = [self.subscribe(e, handler) for e in event]

            def unsubscribe_all() -> None:
                for unsubscribe in unsubscribes:
                    unsubscribe()

            return unsubscribe_all
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
