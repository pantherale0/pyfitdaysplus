"""Connected kitchen scale with a human-centric API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import TracebackType

from ._weight_accessor import WeightAccessor
from .ble.transport import BleTransport
from .config import Config
from .exceptions import NotConnectedError, ProtocolError
from .models import ProtocolVersion, ScaleInfo, Unit, WeightReading
from .protocol.commands import build_app_reply, build_setting_tare, build_setting_unit
from .protocol.constants import DEVICE_TYPE_KG2458, NOTIFY_KITCHEN_SCALE_DATA
from .protocol.notify import parse_weight_notification


class KitchenScaleDevice:
    """One connected ICOMON / Fitdays+ kitchen scale."""

    def __init__(
        self,
        address: str,
        *,
        name: str,
        config: Config | None = None,
        transport: BleTransport | None = None,
    ) -> None:
        self._config = config or Config(address=address, ble_name=name)
        self._transport = transport or BleTransport(address)
        self._latest: WeightReading | None = None
        self._notify_task: asyncio.Task[None] | None = None
        self._readings: asyncio.Queue[WeightReading] = asyncio.Queue()
        self.info = ScaleInfo(
            model=self._config.model,
            ble_name=name,
            address=address,
            device_type=self._config.device_type,
            protocol=_protocol_for_device_type(self._config.device_type),
        )

    @property
    def connected(self) -> bool:
        """Return whether the BLE session is active."""
        return self._transport.connected

    async def connect(self) -> None:
        """Connect, subscribe to notifications, and send the app handshake."""
        if self.connected:
            return
        await self._transport.connect()
        self._notify_task = asyncio.create_task(self._consume_notifications())
        await self._transport.write_command(
            build_app_reply(
                self._config.app_reply_body,
                device_type=self._config.device_type,
            )
        )

    async def disconnect(self) -> None:
        """Close the BLE session."""
        if self._notify_task is not None:
            self._notify_task.cancel()
            try:
                await self._notify_task
            except asyncio.CancelledError:
                pass
            self._notify_task = None
        await self._transport.disconnect()

    async def tare(self) -> None:
        """Send a tare command to the scale."""
        await self._write_setting(
            build_setting_tare(device_type=self._config.device_type)
        )

    async def set_unit(self, unit: Unit) -> None:
        """Change the display/weighing unit."""
        await self._write_setting(
            build_setting_unit(unit, device_type=self._config.device_type)
        )

    async def read_weight(self) -> WeightReading:
        """Wait for the next live weight notification."""
        return await self._readings.get()

    @property
    def weight(self) -> WeightAccessor:
        """Awaitable latest reading: ``reading = await device.weight``."""
        return WeightAccessor(self)

    async def weights(self) -> AsyncIterator[WeightReading]:
        """Iterate live weight readings until disconnected."""
        while self.connected:
            yield await self.read_weight()

    async def __aenter__(self) -> KitchenScaleDevice:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    async def _write_setting(self, frame: bytes) -> None:
        if not self.connected:
            raise NotConnectedError("connect before sending commands")
        await self._transport.write_command(frame)

    async def _consume_notifications(self) -> None:
        try:
            async for payload in self._transport.notifications():
                if not payload:
                    continue
                if payload[0] != NOTIFY_KITCHEN_SCALE_DATA:
                    continue
                try:
                    reading = parse_weight_notification(payload)
                except ProtocolError:
                    continue
                self._latest = reading
                await self._readings.put(reading)
        except asyncio.CancelledError:
            raise


def _protocol_for_device_type(device_type: int) -> ProtocolVersion:
    if device_type == DEVICE_TYPE_KG2458:
        return ProtocolVersion.GENERAL_V2_113
    return ProtocolVersion.GENERAL_V2_113
