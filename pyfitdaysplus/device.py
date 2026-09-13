"""Connected kitchen scale with a human-centric API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from types import TracebackType
from typing import Literal, overload

from .ble.transport import BleTransport
from .config import Config
from .events import Event, EventRegistry, Unsubscribe
from .exceptions import NotConnectedError, ProtocolError
from .models import (
    DISCOVERED_COMPATIBILITY,
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

_LOGGER = logging.getLogger(__name__)


class Device:
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
        self._transport = transport or BleTransport(address, name=name)
        self._weight: WeightReading | None = None
        self._food: FoodInfoNotify | None = None
        self._ack: CommandAck | None = None
        self._capabilities: DeviceCapabilities | None = None
        self._events = EventRegistry()
        self._fun_info_event = asyncio.Event()
        self._notify_task: asyncio.Task[None] | None = None
        self._readings: asyncio.Queue[WeightReading] = asyncio.Queue()
        self._food_selections: asyncio.Queue[FoodInfoNotify] = asyncio.Queue()
        self._on_device_confirm_held = False
        self.info = ScaleInfo(
            model=self._config.model,
            ble_name=name,
            address=address,
            device_type=self._config.device_type,
            protocol=ProtocolVersion.GENERAL_V2_113,
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
    def battery(self) -> BatteryInfo | None:
        """Charge from the last ``funInfo`` (``0xA0``) notify, if present."""
        caps = self._capabilities
        return None if caps is None else caps.battery

    @property
    def weight(self) -> WeightReading | None:
        """Latest cached weight reading from notify ``0xA6``, if any."""
        return self._weight

    @property
    def ack(self) -> CommandAck | None:
        """Latest ``0xA1`` command acknowledgement, if any."""
        return self._ack

    @property
    def food(self) -> FoodInfoNotify | None:
        """Latest cached ``ICFoodInfo`` notify (``0xAF``), if any."""
        return self._food

    async def connect(self) -> None:
        """Connect, subscribe to notifications, and send the app handshake."""
        if self.connected:
            return
        _LOGGER.debug(
            "connecting to %s at %s",
            self.info.ble_name,
            self.info.address,
        )
        await self._transport.connect()
        att_mtu = self._transport.att_mtu
        self._config.mtu = max(SPLIT_DATA_HEADER_LEN + 1, att_mtu - 7)
        _LOGGER.debug(
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
            _LOGGER.debug("funInfo received; sending app_reply")
        except TimeoutError:
            _LOGGER.debug(
                "no funInfo within %.1fs; sending app_reply anyway",
                self._config.fun_info_timeout,
            )
        handshake = build_app_reply(
            self._config.app_reply_body,
            device_type=self._config.device_type,
        )
        _LOGGER.debug("sending app_reply handshake %s", handshake.hex())
        await self._transport.write_command(handshake)
        _LOGGER.debug("handshake sent; waiting for FFB2 notifies")
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
        self._on_device_confirm_held = False
        await self._transport.disconnect()

    async def tare(self) -> None:
        """Send a tare command to the scale."""
        await self._write_setting(
            build_setting_tare(device_type=self._config.device_type)
        )

    async def confirm(self) -> None:
        """
        App confirm over BLE (D2 type 10).

        Front-panel ✓ is ``Event.ON_DEVICE_CONFIRM``.
        """
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
        if self._weight is not None:
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
            caps = _merge_compatibility(caps, extra)
        if caps is not self._capabilities:
            _LOGGER.debug(
                "compatibility=%s flags=0x%08x",
                ",".join(flag.name or str(flag) for flag in caps.flags),
                int(caps.compatibility),
            )
            self._capabilities = caps
            self._events.emit(Event.CAPABILITIES, caps)
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
            updated = _merge_compatibility(caps, extra)
            if updated is caps:
                return
            caps = updated
        self._capabilities = caps
        self._events.emit(Event.CAPABILITIES, caps)

    async def set_nutrition(
        self,
        food_id: int,
        facts: list[NutritionFact],
        *,
        scale: float | None = None,
    ) -> None:
        """
        Send nutrition facts for ``food_id`` (cmd **213 / 0xD5**, native x10).

        Recommended before food-weigh mode: upload facts, then weigh, then
        listen for ✓. Call again after each confirm; the scale only reports
        one on-device confirm per upload. LCD may still show a firmware catalog name;
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

    async def async_get_weight(self) -> WeightReading:
        """Return the cached reading, or wait for the first live notify."""
        cached = self._weight
        if cached is not None:
            return cached
        return await self.read_weight()

    async def read_food_selection(self) -> FoodInfoNotify:
        """Wait for the next ``ICFoodInfo`` notify (``0xAF``) from voice ASR."""
        return await self._food_selections.get()

    @overload
    def subscribe(
        self,
        event: Literal[Event.WEIGHT],
        handler: Callable[[WeightReading], None],
    ) -> Unsubscribe: ...

    @overload
    def subscribe(
        self,
        event: Literal[Event.ON_DEVICE_CONFIRM],
        handler: Callable[[WeightReading], None],
    ) -> Unsubscribe: ...

    @overload
    def subscribe(
        self,
        event: Literal[Event.FOOD],
        handler: Callable[[FoodInfoNotify], None],
    ) -> Unsubscribe: ...

    @overload
    def subscribe(
        self,
        event: Literal[Event.CAPABILITIES],
        handler: Callable[[DeviceCapabilities], None],
    ) -> Unsubscribe: ...

    @overload
    def subscribe(
        self,
        event: Literal[Event.BATTERY],
        handler: Callable[[BatteryInfo], None],
    ) -> Unsubscribe: ...

    def subscribe(self, event: Event, handler: Callable[..., None]) -> Unsubscribe:
        """
        Subscribe to ``event``; returns an unsubscribe callable.

        ``Event.ON_DEVICE_CONFIRM`` is the front-panel ✓ after a food upload
        (history ``0xAC`` on KG2458). The scale emits it **once per food
        upload** — call :meth:`set_nutrition` / :meth:`set_common_food` again
        before the next weigh-and-confirm.
        """
        return self._events.subscribe(event, handler)

    async def weights(self) -> AsyncIterator[WeightReading]:
        """Iterate live weight readings until disconnected."""
        while self.connected:
            yield await self.read_weight()

    async def food_selections(self) -> AsyncIterator[FoodInfoNotify]:
        """Iterate ``ICFoodInfo`` notifies from on-device voice recognition."""
        while self.connected:
            yield await self.read_food_selection()

    async def __aenter__(self) -> Device:
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
            _LOGGER.debug(
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
        _LOGGER.debug(
            "ack cmd=0x%02x state=%s payload=%s",
            ack.command,
            ack.state,
            ack.raw_payload.hex(),
        )
        self._ack = ack

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
            _LOGGER.debug(
                "saved weight %.4g %s food=%s payload=%s",
                reading.value,
                reading.unit.symbol,
                reading.food_id,
                reading.raw_payload.hex(),
            )
            self._events.emit(Event.ON_DEVICE_CONFIRM, reading)

    async def _handle_weight(self, payload: bytes) -> None:
        try:
            reading, is_ok = parse_weight_event(payload)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored weight notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        previous = self._weight
        if previous is not None and previous.unit != reading.unit:
            _LOGGER.debug(
                "unit changed %s -> %s",
                previous.unit.name,
                reading.unit.name,
            )
        if is_ok and not self._on_device_confirm_held:
            _LOGGER.debug("on-device confirm (A6 isOk)")
            self._events.emit(Event.ON_DEVICE_CONFIRM, reading)
        self._on_device_confirm_held = is_ok
        _LOGGER.debug(
            "weight %.4g %s stable=%s tare=%s unit=%s food=%s",
            reading.value,
            reading.unit.symbol,
            reading.stable,
            reading.is_tare,
            reading.unit.name,
            reading.food_id,
        )
        self._weight = reading
        self._events.emit(Event.WEIGHT, reading)
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
        _LOGGER.debug(
            "food notify count=%s foods=%s payload=%s",
            notify.count,
            len(notify.foods),
            notify.raw_payload.hex(),
        )
        self._food = notify
        self._events.emit(Event.FOOD, notify)
        await self._food_selections.put(notify)

    def _handle_capabilities(self, payload: bytes) -> None:
        try:
            capabilities = _keep_discovered(parse_fun_info(payload), self._capabilities)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored funInfo notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        _LOGGER.debug(
            "funInfo flags=0x%08x battery=%s compatibility=%s payload=%s",
            int(capabilities.function_flags),
            None if capabilities.battery is None else capabilities.battery.percent,
            ",".join(flag.name or str(int(flag)) for flag in capabilities.flags),
            capabilities.raw_payload.hex(),
        )
        self._capabilities = capabilities
        self._fun_info_event.set()
        self._events.emit(Event.CAPABILITIES, capabilities)
        if capabilities.battery is not None:
            self._events.emit(Event.BATTERY, capabilities.battery)


def _merge_compatibility(
    caps: DeviceCapabilities, extra: CompatibilityFlag
) -> DeviceCapabilities:
    """Return ``caps`` with additional discovered compatibility bits."""
    if extra & caps.compatibility == extra:
        return caps
    return replace(caps, compatibility=caps.compatibility | extra)


def _keep_discovered(
    caps: DeviceCapabilities, previous: DeviceCapabilities | None
) -> DeviceCapabilities:
    """Keep WEIGHT / FFB4 / DFU bits from an earlier probe of the same session."""
    if previous is None:
        return caps
    extra = previous.compatibility & DISCOVERED_COMPATIBILITY
    return _merge_compatibility(caps, extra)
