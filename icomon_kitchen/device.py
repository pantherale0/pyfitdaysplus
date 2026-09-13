"""Connected kitchen scale with a human-centric API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from types import TracebackType

from ._weight_accessor import CachedWeightAccessor, WeightAccessor
from .ble.transport import BleTransport
from .config import Config
from .events import ListenerList
from .exceptions import NotConnectedError, ProtocolError
from .models import (
    BatteryInfo,
    CommandAck,
    CommonFood,
    CompatibilityFlag,
    DeviceCapabilities,
    DeviceFunction,
    FoodInfoNotify,
    FoodReference,
    NutritionFact,
    ProtocolVersion,
    ScaleInfo,
    Unit,
    WeightReading,
)
from .protocol.commands import (
    build_app_reply,
    build_setting_confirm,
    build_setting_tare,
    build_setting_unit,
)
from .protocol.constants import (
    CHAR_FILE_WRITE_UUID,
    DEVICE_TYPE_KG2458,
    DFU_SERVICE_UUID,
    NOTIFY_FOOD_INFO,
    NOTIFY_FUN_INFO,
    NOTIFY_HISTORY_WEIGHTS,
    NOTIFY_HISTORY_WEIGHTS_ALT,
    NOTIFY_KITCHEN_SCALE_DATA,
    NOTIFY_STATE_ACK,
    SPLIT_DATA_HEADER_LEN,
)
from .protocol.food_write import (
    build_delete_common_foods_frames,
    build_set_common_food_frames,
    build_set_common_food_indexed_frames,
    build_set_nutrition_frames,
)
from .protocol.framing import decode_notify_payload
from .protocol.notify import (
    parse_food_info_notify,
    parse_fun_info,
    parse_history_weight_records,
    parse_state_ack,
    parse_weight_event,
)

FoodSelectionHandler = Callable[[FoodInfoNotify], None]
CapabilitiesHandler = Callable[[DeviceCapabilities], None]
WeightHandler = Callable[[WeightReading], None]
TickHandler = Callable[[WeightReading], None]
Unsubscribe = Callable[[], None]

_LOGGER = logging.getLogger(__name__)


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
        on_weight: WeightHandler | None = None,
        on_tick: TickHandler | None = None,
    ) -> None:
        self._config = config or Config(address=address, ble_name=name)
        self._transport = transport or BleTransport(address)
        self._latest_weight: WeightReading | None = None
        self._latest_food_selection: FoodInfoNotify | None = None
        self._latest_ack: CommandAck | None = None
        self._capabilities: DeviceCapabilities | None = None
        self._fun_info_event = asyncio.Event()
        self._notify_task: asyncio.Task[None] | None = None
        self._readings: asyncio.Queue[WeightReading] = asyncio.Queue()
        self._food_selections: asyncio.Queue[FoodInfoNotify] = asyncio.Queue()
        self._weight_listeners: ListenerList[WeightReading] = ListenerList()
        self._tick_listeners: ListenerList[WeightReading] = ListenerList()
        self._food_selection_listeners: ListenerList[FoodInfoNotify] = ListenerList()
        self._capabilities_listeners: ListenerList[DeviceCapabilities] = ListenerList()
        self._tick_held = False
        self._cached_weight = CachedWeightAccessor(self)
        if on_weight is not None:
            self._weight_listeners.subscribe(on_weight)
        if on_tick is not None:
            self._tick_listeners.subscribe(on_tick)
        if on_food_selection is not None:
            self._food_selection_listeners.subscribe(on_food_selection)
        elif on_food_info is not None:
            self._food_selection_listeners.subscribe(on_food_info)
        if on_capabilities is not None:
            self._capabilities_listeners.subscribe(on_capabilities)
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
        """Latest cached ``funInfo`` capabilities, when the scale sends them."""
        return self._capabilities

    @property
    def latest_battery(self) -> BatteryInfo | None:
        """Charge from the last ``funInfo`` (``0xA0``) notify, if present."""
        caps = self._capabilities
        return None if caps is None else caps.battery

    @property
    def latest_weight(self) -> WeightReading | None:
        """Latest cached weight reading from notify ``0xA6``, updated on each event."""
        return self._latest_weight

    @property
    def latest_ack(self) -> CommandAck | None:
        """Latest ``0xA1`` command acknowledgement, if any."""
        return self._latest_ack

    @property
    def latest_food_selection(self) -> FoodInfoNotify | None:
        """Latest cached ``ICFoodInfo`` notify (``0xAF``), if any."""
        return self._latest_food_selection

    @property
    def cached_weight(self) -> CachedWeightAccessor:
        """
        Sync view of the weight cache.

        Use ``device.cached_weight.grams`` from non-async code; returns ``None``
        until the first weight notification arrives.
        """
        return self._cached_weight

    @property
    def weight(self) -> WeightAccessor:
        """Awaitable latest reading: ``reading = await device.weight``."""
        return WeightAccessor(self)

    async def connect(self) -> None:
        """Connect, subscribe to notifications, and send the app handshake."""
        if self.connected:
            return
        _LOGGER.info(
            "connecting to %s at %s",
            self.info.ble_name,
            self.info.address,
        )
        await self._transport.connect()
        att_mtu = self._transport.att_mtu
        self._config.mtu = max(SPLIT_DATA_HEADER_LEN + 1, att_mtu - 7)
        _LOGGER.info(
            "ATT MTU=%s split body max=%s",
            att_mtu,
            self._config.mtu,
        )
        self._notify_task = asyncio.create_task(self._consume_notifications())
        try:
            await asyncio.wait_for(
                self._fun_info_event.wait(),
                timeout=self._config.fun_info_timeout,
            )
            _LOGGER.info("funInfo received; sending app_reply")
        except TimeoutError:
            _LOGGER.info(
                "no funInfo within %.1fs; sending app_reply anyway",
                self._config.fun_info_timeout,
            )
        handshake = build_app_reply(
            self._config.app_reply_body,
            device_type=self._config.device_type,
        )
        _LOGGER.info("sending app_reply handshake %s", handshake.hex())
        await self._transport.write_command(handshake)
        _LOGGER.info("handshake sent; waiting for FFB2 notifies")
        await self.probe_compatibility()

    async def disconnect(self) -> None:
        """Close the BLE session."""
        if self._notify_task is not None:
            self._notify_task.cancel()
            try:
                await self._notify_task
            except asyncio.CancelledError:
                pass
            self._notify_task = None
        self._fun_info_event.clear()
        self._capabilities = None
        self._tick_held = False
        await self._transport.disconnect()

    async def tare(self) -> None:
        """Send a tare command to the scale."""
        await self._write_setting(
            build_setting_tare(device_type=self._config.device_type)
        )

    async def confirm(self) -> None:
        """Tell the scale the current food/weight was accepted (D2 type 10)."""
        await self._write_setting(
            build_setting_confirm(device_type=self._config.device_type)
        )

    async def set_unit(self, unit: Unit) -> None:
        """Change the display/weighing unit."""
        await self._write_setting(
            build_setting_unit(unit, device_type=self._config.device_type)
        )

    async def probe_compatibility(self) -> DeviceCapabilities:
        """
        Refresh ``capabilities`` from funInfo, live weight, and GATT.

        Does not send extra command writes. Nordic DFU / FFB4 presence is
        discovered from the current session's service table.
        """
        extra = CompatibilityFlag(0)
        if self._latest_weight is not None:
            extra |= CompatibilityFlag.WEIGHT
        if self._transport.has_characteristic(CHAR_FILE_WRITE_UUID):
            extra |= CompatibilityFlag.FILE_TRANSFER
        if self._transport.has_service(DFU_SERVICE_UUID):
            extra |= CompatibilityFlag.OTA_DFU
        caps = self._capabilities
        if caps is None:
            caps = DeviceCapabilities(
                function_flags=DeviceFunction(0),
                compatibility=extra,
            )
        else:
            caps = caps.with_discovered(extra)
        if caps is not self._capabilities:
            _LOGGER.info(
                "compatibility=%s flags=0x%08x",
                ",".join(flag.name or str(flag) for flag in caps.flags),
                int(caps.compatibility),
            )
            self._capabilities = caps
            self._capabilities_listeners.emit(caps)
        return caps

    def _merge_discovered(self, extra: CompatibilityFlag) -> None:
        """OR ``extra`` into cached compatibility without a GATT scan."""
        caps = self._capabilities
        if caps is None:
            if not extra:
                return
            caps = DeviceCapabilities(
                function_flags=DeviceFunction(0),
                compatibility=extra,
            )
        else:
            updated = caps.with_discovered(extra)
            if updated is caps:
                return
            caps = updated
        self._capabilities = caps
        self._capabilities_listeners.emit(caps)

    async def set_nutrition(
        self,
        food_id: int,
        facts: list[NutritionFact],
        *,
        scale: float | None = None,
    ) -> None:
        """
        Send nutrition facts for ``food_id`` (cmd **213 / 0xD5**, native ×10).

        Recommended before food-weigh mode: upload facts, then weigh, then
        listen for ✓. Call again after each confirm; the scale only reports
        one tick per upload. LCD may still show a firmware catalog name;
        the values you pass here are the ones to trust.
        """
        frames = build_set_nutrition_frames(
            food_id,
            facts,
            device_type=self._config.device_type,
            mtu=self._config.mtu,
            scale=scale,
        )
        await self._write_frames(frames)

    async def set_common_food(
        self,
        food: CommonFood,
        *,
        scale: float | None = None,
    ) -> None:
        """
        Upload a custom food entry (cmd **214 / 0xD6**, split when long).

        Preferred together with :meth:`set_nutrition` **before** entering
        food-weigh mode. On KG2458 the LCD name may stay a catalog label
        (for example “MILK WHOLE”); pass your own facts at runtime anyway.
        """
        frames = build_set_common_food_frames(
            food,
            device_type=self._config.device_type,
            mtu=self._config.mtu,
            scale=scale,
        )
        await self._write_frames(frames)

    async def set_common_food_indexed(
        self,
        food_index: int,
        food: CommonFood,
        *,
        scale: float | None = None,
    ) -> None:
        """Upload an indexed custom food entry (cmd **215 / 0xD7**)."""
        frames = build_set_common_food_indexed_frames(
            food_index,
            food,
            device_type=self._config.device_type,
            mtu=self._config.mtu,
            scale=scale,
        )
        await self._write_frames(frames)

    async def delete_common_foods(
        self,
        entries: list[FoodReference],
        *,
        use_alt_delete: bool = True,
    ) -> None:
        """Delete custom foods (cmd **220 / 0xDC** on protocol 113 by default)."""
        frames = build_delete_common_foods_frames(
            entries,
            device_type=self._config.device_type,
            mtu=self._config.mtu,
            use_alt_delete=use_alt_delete,
        )
        await self._write_frames(frames)

    async def read_weight(self) -> WeightReading:
        """Wait for the next live weight notification."""
        return await self._readings.get()

    async def read_food_selection(self) -> FoodInfoNotify:
        """Wait for the next ``ICFoodInfo`` notify (``0xAF``) from voice ASR."""
        return await self._food_selections.get()

    async def read_food_info(self) -> FoodInfoNotify:
        """Alias for :meth:`read_food_selection`."""
        return await self.read_food_selection()

    def subscribe_weight(self, handler: WeightHandler) -> Unsubscribe:
        """Subscribe to live weight notifications; returns an unsubscribe callable."""
        return self._weight_listeners.subscribe(handler)

    def subscribe_tick(self, handler: TickHandler) -> Unsubscribe:
        """
        Subscribe to hardware ✓ (food confirm).

        On KG2458 this is a history ``0xAC`` notify, not A6 ``isOk``. The
        scale emits it **once per food upload**. Call
        :meth:`set_nutrition` / :meth:`set_common_food` again before the
        next weigh-and-confirm. Returns an unsubscribe callable.
        """
        return self._tick_listeners.subscribe(handler)

    def subscribe_food_selection(self, handler: FoodSelectionHandler) -> Unsubscribe:
        """Subscribe to ``ICFoodInfo`` (``0xAF``) voice selection notifications."""
        return self._food_selection_listeners.subscribe(handler)

    def subscribe_capabilities(self, handler: CapabilitiesHandler) -> Unsubscribe:
        """Subscribe to ``funInfo`` (``0xA0``) capability notifications."""
        return self._capabilities_listeners.subscribe(handler)

    def set_weight_handler(self, handler: WeightHandler | None) -> None:
        """Replace weight subscribers with a single handler, or clear when ``None``."""
        self._weight_listeners.clear()
        if handler is not None:
            self._weight_listeners.subscribe(handler)

    def set_tick_handler(self, handler: TickHandler | None) -> None:
        """Replace tick subscribers with a single handler, or clear when ``None``."""
        self._tick_listeners.clear()
        if handler is not None:
            self._tick_listeners.subscribe(handler)

    def set_food_selection_handler(
        self,
        handler: FoodSelectionHandler | None,
    ) -> None:
        """
        Replace food-selection subscribers with one handler.

        Pass ``None`` to clear all subscribers.
        """
        self._food_selection_listeners.clear()
        if handler is not None:
            self._food_selection_listeners.subscribe(handler)

    def set_food_info_handler(self, handler: FoodSelectionHandler | None) -> None:
        """Alias for :meth:`set_food_selection_handler`."""
        self.set_food_selection_handler(handler)

    def set_capabilities_handler(self, handler: CapabilitiesHandler | None) -> None:
        """Replace capability subscribers with one handler, or clear when ``None``."""
        self._capabilities_listeners.clear()
        if handler is not None:
            self._capabilities_listeners.subscribe(handler)

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

    async def _write_frames(self, frames: list[bytes]) -> None:
        if not self.connected:
            raise NotConnectedError("connect before sending commands")
        for frame in frames:
            await self._transport.write_command(frame)

    async def _consume_notifications(self) -> None:
        try:
            async for payload in self._transport.notifications():
                if not payload:
                    _LOGGER.debug("ignored empty notify")
                    continue
                await self._dispatch_notification(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("notification listener stopped")
            raise

    async def _dispatch_notification(self, payload: bytes) -> None:
        try:
            notify_type, _inner = decode_notify_payload(payload)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        _LOGGER.debug(
            "dispatch notify type=0x%02x payload=%s",
            notify_type,
            payload.hex(),
        )
        if notify_type == NOTIFY_KITCHEN_SCALE_DATA:
            await self._handle_weight(payload)
        elif notify_type == NOTIFY_FOOD_INFO:
            await self._handle_food_info(payload)
        elif notify_type == NOTIFY_FUN_INFO:
            self._handle_capabilities(payload)
        elif notify_type == NOTIFY_STATE_ACK:
            self._handle_ack(payload)
        elif notify_type in {NOTIFY_HISTORY_WEIGHTS, NOTIFY_HISTORY_WEIGHTS_ALT}:
            self._handle_history_weights(payload)
        else:
            _LOGGER.info(
                "unhandled notify type=0x%02x payload=%s",
                notify_type,
                payload.hex(),
            )

    def _handle_ack(self, payload: bytes) -> None:
        try:
            ack = parse_state_ack(payload)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored state ack: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        _LOGGER.info(
            "ack cmd=0x%02x state=%s payload=%s",
            ack.command,
            ack.state,
            ack.raw_payload.hex(),
        )
        self._latest_ack = ack

    def _handle_history_weights(self, payload: bytes) -> None:
        try:
            records = parse_history_weight_records(payload)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored history notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        for reading in records:
            _LOGGER.info(
                "saved weight %.4g %s food=%s payload=%s",
                reading.value,
                reading.unit.symbol,
                reading.food_id,
                reading.raw_payload.hex(),
            )
            self._tick_listeners.emit(reading)

    async def _handle_weight(self, payload: bytes) -> None:
        try:
            reading, tick = parse_weight_event(payload)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored weight notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        previous = self._latest_weight
        if previous is not None and previous.unit != reading.unit:
            _LOGGER.info(
                "unit changed %s -> %s",
                previous.unit.name,
                reading.unit.name,
            )
        if tick and not self._tick_held:
            _LOGGER.info("tick on scale")
            self._tick_listeners.emit(reading)
        self._tick_held = tick
        _LOGGER.info(
            "weight %.4g %s stable=%s tare=%s unit=%s food=%s",
            reading.value,
            reading.unit.symbol,
            reading.stable,
            reading.is_tare,
            reading.unit.name,
            reading.food_id,
        )
        self._latest_weight = reading
        self._weight_listeners.emit(reading)
        await self._readings.put(reading)
        self._merge_discovered(CompatibilityFlag.WEIGHT)

    async def _handle_food_info(self, payload: bytes) -> None:
        try:
            notify = parse_food_info_notify(payload)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored food notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        _LOGGER.info(
            "food notify count=%s foods=%s payload=%s",
            notify.count,
            len(notify.foods),
            notify.raw_payload.hex(),
        )
        self._latest_food_selection = notify
        self._food_selection_listeners.emit(notify)
        await self._food_selections.put(notify)

    def _handle_capabilities(self, payload: bytes) -> None:
        try:
            capabilities = parse_fun_info(payload).absorb_discovered(self._capabilities)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored funInfo notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        _LOGGER.info(
            "funInfo flags=0x%08x battery=%s compatibility=%s payload=%s",
            int(capabilities.function_flags),
            None if capabilities.battery is None else capabilities.battery.percent,
            ",".join(flag.name or str(int(flag)) for flag in capabilities.flags),
            capabilities.raw_payload.hex(),
        )
        self._capabilities = capabilities
        self._fun_info_event.set()
        self._capabilities_listeners.emit(capabilities)


def _protocol_for_device_type(device_type: int) -> ProtocolVersion:
    if device_type == DEVICE_TYPE_KG2458:
        return ProtocolVersion.GENERAL_V2_113
    return ProtocolVersion.GENERAL_V2_113
