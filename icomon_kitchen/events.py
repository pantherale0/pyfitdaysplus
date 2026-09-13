"""Lightweight multi-subscriber event dispatch for device notifications."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")
Unsubscribe = Callable[[], None]


class ListenerList(Generic[T]):
    """Thread-safe enough for asyncio: mutate on the event loop, emit synchronously."""

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: list[Callable[[T], None]] = []

    def subscribe(self, handler: Callable[[T], None]) -> Unsubscribe:
        """Register ``handler`` and return a callable that removes it."""
        self._listeners.append(handler)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(handler)
            except ValueError:
                pass

        return unsubscribe

    def clear(self) -> None:
        """Remove every registered handler."""
        self._listeners.clear()

    def emit(self, value: T) -> None:
        """Invoke all handlers with ``value``."""
        for handler in list(self._listeners):
            handler(value)
