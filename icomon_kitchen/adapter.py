"""Low-level ble connection handling."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import TYPE_CHECKING

from .ble.backend import BleBackend, DefaultBleBackend
from .ble.transport import BleTransport
from .config import Config

if TYPE_CHECKING:
    from bleak import BleakClient

_NOT_CONNECTED = "You're not connected yet — call connect() first."


class Adapter(ABC):
    """Common connect/disconnect behaviour for BLE adapters."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def create_transport(self, address: str) -> BleTransport: ...

    async def __aenter__(self) -> Adapter:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()


class BleAdapter(Adapter):
    """Talk to a Bluetooth Low Energy device through bleak."""

    def __init__(
        self,
        config: Config,
        *,
        backend: BleBackend | None = None,
    ) -> None:
        self._config = config
        self._backend = backend or DefaultBleBackend()
        self._client: BleakClient | None = None

    @property
    def client(self) -> BleakClient:
        """The bleak client, available after `connect()`."""
        if self._client is None:
            raise RuntimeError(_NOT_CONNECTED)
        return self._client

    def create_transport(self, address: str) -> BleTransport:
        """Return a GATT transport bound to ``address``."""
        return BleTransport(address, backend=self._backend)

    async def connect(self) -> None:
        if not self._config.address:
            msg = "Config.address is required before connect()"
            raise RuntimeError(msg)
        self._client = self._backend.client(self._config.address)
        await self._client.connect()

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None


def create_adapter(
    config: Config,
    *,
    backend: BleBackend | None = None,
) -> Adapter:
    """Build the default BLE adapter for ``config``."""
    return BleAdapter(config, backend=backend)
