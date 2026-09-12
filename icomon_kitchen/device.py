"""Connected kitchen scale with a human-centric API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from types import TracebackType

from ._weight_accessor import WeightAccessor
from .ble.transport import BleTransport
from .config import Config
from .exceptions import NotConnectedError, ProtocolError
from .models import (
    DeviceCapabilities,
    FoodInfoNotify,
    ProtocolVersion,
    ScaleInfo,
    Unit,
    WeightReading,
)
from .protocol.commands import build_app_reply, build_setting_tare, build_setting_unit
from .protocol.constants import (
    DEVICE_TYPE_KG2458,
    NOTIFY_FOOD_INFO,
    NOTIFY_FUN_INFO,
    NOTIFY_KITCHEN_SCALE_DATA,
)
from .protocol.notify import (
    parse_food_info_notify,
    parse_fun_info,
    parse_weight_notification,
)

FoodSelectionHandler = Callable[[FoodInfoNotify], None]
CapabilitiesHandler = Callable[[DeviceCapabilities], None]


class KitchenScaleDevice:
    """One connected ICOMON / Fitdays+ kitchen scale."""

    def __init__(
        self,
        address: str,
        *,
        name: str,
        config: Config | None = None,
        transport: BleTransport | None = None,
        on_food_selection: FoodSelectionHandler | None = None,
        on_capabilities: CapabilitiesHandler | None = None,
        on_food_info: FoodSelectionHandler | None = None,
    ) -> None:
        self._config = config or Config(address=address, ble_name=name)
        self._transport = transport or BleTransport(address)
        self._latest: WeightReading | None = None
        self._capabilities: DeviceCapabilities | None = None
        self._notify_task: asyncio.Task[None] | None = None
        self._readings: asyncio.Queue[WeightReading] = asyncio.Queue()
        self._food_selections: asyncio.Queue[FoodInfoNotify] = asyncio.Queue()
        self._on_food_selection = on_food_selection or on_food_info
        self._on_capabilities = on_capabilities
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

    @property
    def capabilities(self) -> DeviceCapabilities | None:
        """Latest ``funInfo`` capabilities, when the scale sends them."""
        return self._capabilities

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

    async def read_food_selection(self) -> FoodInfoNotify:
        """Wait for the next ``ICFoodInfo`` notify (``0xAF``) from voice ASR."""
        return await self._food_selections.get()

    async def read_food_info(self) -> FoodInfoNotify:
        """Alias for :meth:`read_food_selection`."""
        return await self.read_food_selection()

    @property
    def weight(self) -> WeightAccessor:
        """Awaitable latest reading: ``reading = await device.weight``."""
        return WeightAccessor(self)

    async def weights(self) -> AsyncIterator[WeightReading]:
        """Iterate live weight readings until disconnected."""
        while self.connected:
            yield await self.read_weight()

    async def food_selections(self) -> AsyncIterator[FoodInfoNotify]:
        """Iterate ``ICFoodInfo`` notifies from on-device voice recognition."""
        while self.connected:
            yield await self.read_food_selection()

    async def food_infos(self) -> AsyncIterator[FoodInfoNotify]:
        """Alias for :meth:`food_selections`."""
        async for notify in self.food_selections():
            yield notify

    def set_food_selection_handler(
        self,
        handler: FoodSelectionHandler | None,
    ) -> None:
        """Register a callback for ``ICFoodInfo`` (``0xAF``) notifications."""
        self._on_food_selection = handler

    def set_food_info_handler(self, handler: FoodSelectionHandler | None) -> None:
        """Alias for :meth:`set_food_selection_handler`."""
        self.set_food_selection_handler(handler)

    def set_capabilities_handler(self, handler: CapabilitiesHandler | None) -> None:
        """Register a callback for ``funInfo`` (0xA0) capability notifications."""
        self._on_capabilities = handler

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
                await self._dispatch_notification(payload)
        except asyncio.CancelledError:
            raise

    async def _dispatch_notification(self, payload: bytes) -> None:
        notify_type = payload[0]
        if notify_type == NOTIFY_KITCHEN_SCALE_DATA:
            await self._handle_weight(payload)
        elif notify_type == NOTIFY_FOOD_INFO:
            await self._handle_food_info(payload)
        elif notify_type == NOTIFY_FUN_INFO:
            self._handle_capabilities(payload)

    async def _handle_weight(self, payload: bytes) -> None:
        try:
            reading = parse_weight_notification(payload)
        except ProtocolError:
            return
        self._latest = reading
        await self._readings.put(reading)

    async def _handle_food_info(self, payload: bytes) -> None:
        try:
            notify = parse_food_info_notify(payload)
        except ProtocolError:
            return
        await self._food_selections.put(notify)
        if self._on_food_selection is not None:
            self._on_food_selection(notify)

    def _handle_capabilities(self, payload: bytes) -> None:
        try:
            capabilities = parse_fun_info(payload)
        except ProtocolError:
            return
        self._capabilities = capabilities
        if self._on_capabilities is not None:
            self._on_capabilities(capabilities)


def _protocol_for_device_type(device_type: int) -> ProtocolVersion:
    if device_type == DEVICE_TYPE_KG2458:
        return ProtocolVersion.GENERAL_V2_113
    return ProtocolVersion.GENERAL_V2_113
