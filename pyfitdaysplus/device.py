"""Connected kitchen scale with a human-centric API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from types import TracebackType
from typing import Literal, overload

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .ble.gatt import (
    ScaleCharacteristics,
    att_mtu,
    discover_scale_characteristics,
    gatt_has_uuid,
    refresh_att_mtu,
)
from .events import Event, EventRegistry, Unsubscribe
from .exceptions import NotConnectedError, ProtocolError
from .models import (
    DISCOVERED_COMPATIBILITY,
    FOOD_WEIGH_CLEAR,
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
    build_read_history,
    build_setting_confirm,
    build_setting_tare,
    build_setting_unit,
)
from .protocol.constants import (
    CHAR_FILE_WRITE_UUID,
    DEFAULT_BLE_NAME,
    DEFAULT_MODEL,
    DEFAULT_MTU,
    DEVICE_TYPE_KG2458,
    DFU_SERVICE_UUID,
    HISTORY_PAGE_SIZE,
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
    """One ICOMON / Fitdays+ kitchen scale, connected or waiting to be seen."""

    def __init__(
        self,
        ble_device: BLEDevice | None = None,
        advertisement_data: AdvertisementData | None = None,
        *,
        address: str | None = None,
        name: str | None = None,
        device_type: int = DEVICE_TYPE_KG2458,
        fun_info_timeout: float = 3.0,
    ) -> None:
        resolved = ble_device.address if ble_device is not None else (address or "")
        if not resolved:
            raise ValueError("provide a BLEDevice or an address")
        self._ble_device = ble_device
        self._advertisement_data = advertisement_data
        self._address = resolved
        if ble_device is not None and ble_device.name:
            self._name = ble_device.name
        else:
            self._name = name or DEFAULT_BLE_NAME
        self._device_type = device_type
        self._fun_info_timeout = fun_info_timeout
        self._mtu = DEFAULT_MTU
        self._client: BleakClient | None = None
        self._chars: ScaleCharacteristics | None = None
        self._notify_started = False
        self._connect_lock = asyncio.Lock()
        self._weight: WeightReading | None = None
        self._food: FoodInfoNotify | None = None
        self._ack: CommandAck | None = None
        self._capabilities: DeviceCapabilities | None = None
        self._events = EventRegistry()
        self._fun_info_event = asyncio.Event()
        self._readings: asyncio.Queue[WeightReading] = asyncio.Queue()
        self._food_selections: asyncio.Queue[FoodInfoNotify] = asyncio.Queue()
        self._on_device_confirm_held = False
        self._history: tuple[WeightReading, ...] = ()
        self._history_lock = asyncio.Lock()
        self._history_batch: list[WeightReading] | None = None
        self._history_received = asyncio.Event()
        self._food_weigh: CommonFood | None = None
        self._food_weigh_lock = asyncio.Lock()
        self._food_weigh_seen_weight = False
        self._food_weigh_sent_on_weight = False

    @property
    def name(self) -> str:
        """Advertised BLE name, or the KG2458 default."""
        return self._name

    @property
    def address(self) -> str:
        """BLE address, from construction or the latest ``BLEDevice``."""
        return self._address

    @property
    def info(self) -> ScaleInfo:
        """Identity derived from the BLE handle, or the stored address."""
        return ScaleInfo(
            model=DEFAULT_MODEL,
            ble_name=self.name,
            address=self.address,
            device_type=self._device_type,
            protocol=ProtocolVersion.GENERAL_V2_113,
        )

    @property
    def connected(self) -> bool:
        """Return whether the BLE session is active."""
        return self._client is not None and self._client.is_connected

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

    @property
    def history(self) -> tuple[WeightReading, ...]:
        """Last :meth:`read_history` result, or empty before the first pull."""
        return self._history

    @property
    def food_weigh(self) -> CommonFood | None:
        """Food currently in food-weigh mode, or ``None`` when idle."""
        return self._food_weigh

    @property
    def ble_device(self) -> BLEDevice | None:
        """BLE device handle used for the next connection, if known."""
        return self._ble_device

    @property
    def advertisement_data(self) -> AdvertisementData | None:
        """Latest advertisement from the caller, if provided."""
        return self._advertisement_data

    def set_ble_device_and_advertisement_data(
        self,
        ble_device: BLEDevice,
        advertisement_data: AdvertisementData | None = None,
    ) -> None:
        """
        Update the BLE path used on the next connection.

        Home Assistant calls this when the scanner sees a new advertisement
        (adapter change, proxy switch, stronger RSSI).
        """
        self._ble_device = ble_device
        self._advertisement_data = advertisement_data
        self._address = ble_device.address
        if ble_device.name:
            self._name = ble_device.name

    async def connect(self) -> None:
        """Connect, subscribe to notifications, and send the app handshake."""
        async with self._connect_lock:
            if self.connected:
                return
            ble_device = self._ble_device
            if ble_device is None:
                raise NotConnectedError(
                    f"no BLEDevice for {self.address}; "
                    "call set_ble_device_and_advertisement_data "
                    "when the scale is in range"
                )
            _LOGGER.debug("connecting to %s at %s", self.name, self.address)
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                disconnected_callback=self._on_disconnect,
                use_services_cache=True,
            )
            self._client = client
            try:
                chars = discover_scale_characteristics(client.services)
                self._chars = chars
                _LOGGER.debug("enabling notifications on %s", chars.notify_uuid)
                await client.start_notify(chars.notify_uuid, self._on_notify)
                self._notify_started = True
                await refresh_att_mtu(client)
            except BaseException:
                _LOGGER.debug("connect failed for %s", self.address, exc_info=True)
                await self._close_session()
                raise
            mtu = att_mtu(client)
            self._mtu = max(SPLIT_DATA_HEADER_LEN + 1, mtu - 7)
            _LOGGER.debug("ATT MTU=%s split body max=%s", mtu, self._mtu)
            try:
                await asyncio.wait_for(
                    self._fun_info_event.wait(),
                    timeout=self._fun_info_timeout,
                )
                _LOGGER.debug("funInfo received; sending app_reply")
            except TimeoutError:
                _LOGGER.debug(
                    "no funInfo within %.1fs; sending app_reply anyway",
                    self._fun_info_timeout,
                )
            handshake = build_app_reply(device_type=self._device_type)
            _LOGGER.debug("sending app_reply handshake %s", handshake.hex())
            await self._write_command(handshake)
            _LOGGER.debug("handshake sent; waiting for FFB2 notifies")
            await self.probe_compatibility()
            self._events.emit(Event.CONNECT, self.address)

    def _on_disconnect(self, client: BleakClient) -> None:
        if client is not self._client:
            return
        _LOGGER.debug("disconnected from %s", self.address)
        self._reset_session_state()

    def _on_notify(
        self,
        characteristic: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        payload = bytes(data)
        if not payload:
            _LOGGER.debug("ignored empty notify")
            return
        _LOGGER.debug("notify %s: %s", characteristic.uuid, payload.hex())
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._dispatch_notification(payload))
        task.add_done_callback(_log_dispatch_error)

    async def disconnect(self) -> None:
        """Close the BLE session."""
        async with self._connect_lock:
            await self._close_session()

    def _reset_session_state(self) -> None:
        """Drop in-memory GATT state. Emits ``Event.DISCONNECT`` if a client was set."""
        had_client = self._client is not None
        self._fun_info_event.clear()
        self._capabilities = None
        self._on_device_confirm_held = False
        self._history_batch = None
        self._history_received.set()
        was_weighing = self._food_weigh is not None
        self._clear_food_weigh_state()
        if was_weighing:
            self._events.emit(Event.FOOD_WEIGH, None)
        self._chars = None
        self._notify_started = False
        self._client = None
        if had_client:
            self._events.emit(Event.DISCONNECT, self.address)

    async def _close_session(self) -> None:
        chars = self._chars
        notify_started = self._notify_started
        client = self._client
        self._reset_session_state()
        if client is None:
            return
        try:
            if notify_started and chars is not None and client.is_connected:
                await client.stop_notify(chars.notify_uuid)
        finally:
            if client.is_connected:
                await client.disconnect()

    async def tare(self) -> None:
        """Send a tare command to the scale."""
        await self._write_command(build_setting_tare(device_type=self._device_type))

    async def confirm(self) -> None:
        """
        App confirm over BLE (D2 type 10).

        Front-panel ✓ is ``Event.ON_DEVICE_CONFIRM``.
        """
        await self._write_command(build_setting_confirm(device_type=self._device_type))

    async def set_unit(self, unit: Unit) -> None:
        """Change the display/weighing unit."""
        await self._write_command(
            build_setting_unit(unit, device_type=self._device_type)
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
        client = self._client
        if client is not None:
            if gatt_has_uuid(client, CHAR_FILE_WRITE_UUID, chars=True):
                extra |= CompatibilityFlag.FILE_TRANSFER
            if gatt_has_uuid(client, DFU_SERVICE_UUID, chars=False):
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

        Low-level write. KG2458 food-weigh mode uses D6 only
        (:meth:`start_food_weigh`); keep D5 for SKUs that still need it.
        """
        frames = build_set_nutrition_frames(
            food_id,
            facts,
            device_type=self._device_type,
            mtu=self._mtu,
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

        Low-level write. For food-weigh mode use :meth:`start_food_weigh`.
        """
        await self._write_common_food(food, scale=scale)

    async def start_food_weigh(self, food: CommonFood) -> None:
        """
        Enter food-weigh mode with ``food`` (cmd **214 / 0xD6**).

        Integrators only need this plus :meth:`stop_food_weigh`. The session
        matches Fitdays+ on KG2458:

        * D6 immediately (even at 0 g).
        * D6 again when a stable non-zero weight is present.
        * After front-panel ✓, D6 the same food again (re-arm).
        * When the plate returns to 0 g, D6 clear and the session ends.

        Does **not** send D5. :meth:`set_nutrition` remains for SKUs that need
        it. Listen for :attr:`Event.ON_DEVICE_CONFIRM` as usual; do not upload
        again yourself.
        """
        async with self._food_weigh_lock:
            self._food_weigh = food
            self._food_weigh_seen_weight = False
            self._food_weigh_sent_on_weight = False
            await self._write_common_food(food)
            reading = self._weight
            if reading is not None and reading.stable and reading.milligrams > 0:
                self._food_weigh_seen_weight = True
                await self._write_common_food(food)
                self._food_weigh_sent_on_weight = True
            self._events.emit(Event.FOOD_WEIGH, food)

    async def stop_food_weigh(self) -> None:
        """Leave food-weigh mode (D6 clear: ``foodId=0``, empty name, 100 g)."""
        async with self._food_weigh_lock:
            if self._food_weigh is None:
                return
            await self._write_food_weigh_clear()

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
            device_type=self._device_type,
            mtu=self._mtu,
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
            device_type=self._device_type,
            mtu=self._mtu,
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

    async def read_history(
        self,
        *,
        idle_timeout: float = 1.5,
        page_size: int = HISTORY_PAGE_SIZE,
        max_pages: int = 20,
    ) -> tuple[WeightReading, ...]:
        """
        Pull stored ✓ records from the scale (cmd **212 / 0xD4**).

        Fitdays+ does this after connect. Each ``0xAC`` is acked with D1
        ``00 ac 00`` and is **not** emitted as ``Event.ON_DEVICE_CONFIRM``.
        Pages of ``page_size`` or more trigger another D4 until a short page
        or an idle gap. Stops after ``max_pages`` even if pages stay full.
        """
        async with self._history_lock:
            collected: list[WeightReading] = []
            pages = 0
            while pages < max_pages:
                page = await self._pull_history_page(idle_timeout)
                pages += 1
                collected.extend(page)
                if len(page) < page_size:
                    break
            self._history = tuple(collected)
            return self._history

    async def _pull_history_page(self, idle_timeout: float) -> list[WeightReading]:
        page: list[WeightReading] = []
        self._history_batch = page
        self._history_received.clear()
        try:
            await self._write_command(build_read_history(device_type=self._device_type))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + idle_timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        self._history_received.wait(),
                        timeout=remaining,
                    )
                except TimeoutError:
                    break
                self._history_received.clear()
                deadline = loop.time() + idle_timeout
            return list(page)
        finally:
            self._history_batch = None

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
        event: Literal[Event.HISTORY],
        handler: Callable[[WeightReading], None],
    ) -> Unsubscribe: ...

    @overload
    def subscribe(
        self,
        event: Literal[Event.FOOD_WEIGH],
        handler: Callable[[CommonFood | None], None],
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

    @overload
    def subscribe(
        self,
        event: Literal[Event.CONNECT],
        handler: Callable[[str], None],
    ) -> Unsubscribe: ...

    @overload
    def subscribe(
        self,
        event: Literal[Event.DISCONNECT],
        handler: Callable[[str], None],
    ) -> Unsubscribe: ...

    def subscribe(
        self,
        event: Event | list[Event],
        handler: Callable[..., None],
    ) -> Unsubscribe:
        """
        Subscribe to ``event``; returns an unsubscribe callable.

        ``event`` may be one :class:`Event` or a list (same handler, one unsubscribe).

        ``Event.ON_DEVICE_CONFIRM`` is the front-panel ✓ after a food upload
        (history ``0xAC`` on KG2458). During :meth:`start_food_weigh` the
        library re-arms D6 for you; one ✓ per armed D6.

        ``Event.HISTORY`` is a stored ``0xAC`` record during
        :meth:`read_history` (D4 dump), not a live ✓.

        ``Event.FOOD_WEIGH`` is the armed food, or ``None`` when the session
        ends (0 g clear, :meth:`stop_food_weigh`, or disconnect).

        ``Event.CONNECT`` / ``Event.DISCONNECT`` are the GATT session
        lifecycle; both pass the scale address.
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

    async def _write_command(self, frame: bytes) -> None:
        client, chars = self._require_session()
        _LOGGER.debug(
            "write FFB1 response=%s payload=%s",
            chars.write_with_response,
            frame.hex(),
        )
        await client.write_gatt_char(
            chars.write_uuid,
            frame,
            response=chars.write_with_response,
        )

    async def _write_file(self, data: bytes) -> None:
        client, chars = self._require_session()
        if chars.file_write_uuid is None:
            msg = "FFB4 file-write characteristic is not present on this scale"
            raise ProtocolError(msg)
        _LOGGER.debug(
            "write FFB4 response=%s payload=%s",
            chars.file_write_with_response,
            data.hex(),
        )
        await client.write_gatt_char(
            chars.file_write_uuid,
            data,
            response=chars.file_write_with_response,
        )

    async def _write_frames(self, frames: list[bytes]) -> None:
        for frame in frames:
            await self._write_command(frame)

    def _require_session(self) -> tuple[BleakClient, ScaleCharacteristics]:
        client = self._client
        chars = self._chars
        if client is None or chars is None or not client.is_connected:
            raise NotConnectedError("connect before sending commands")
        return client, chars

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
            await self._handle_history_weights(notify_type, payload)
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

    async def _handle_history_weights(self, notify_type: int, payload: bytes) -> None:
        try:
            records = parse_history_weight_records(payload)
        except ProtocolError as exc:
            _LOGGER.debug(
                "ignored history notify: %s payload=%s",
                exc,
                payload.hex(),
            )
            return
        batch = self._history_batch
        for reading in records:
            _LOGGER.debug(
                "saved weight %.4g %s food=%s at=%s payload=%s",
                reading.value,
                reading.unit.symbol,
                reading.food_id,
                None
                if reading.recorded_at is None
                else reading.recorded_at.isoformat(),
                reading.raw_payload.hex(),
            )
            if batch is not None:
                batch.append(reading)
                self._history_received.set()
                self._events.emit(Event.HISTORY, reading)
            else:
                self._events.emit(Event.ON_DEVICE_CONFIRM, reading)
        await self._ack_history_notify(notify_type)
        if batch is None:
            await self._rearm_food_weigh()

    async def _ack_history_notify(self, notify_type: int) -> None:
        try:
            await self._write_command(
                build_app_reply(
                    notify_type=notify_type,
                    device_type=self._device_type,
                )
            )
        except NotConnectedError:
            return

    def _clear_food_weigh_state(self) -> None:
        self._food_weigh = None
        self._food_weigh_seen_weight = False
        self._food_weigh_sent_on_weight = False

    async def _write_common_food(
        self,
        food: CommonFood,
        *,
        scale: float | None = None,
    ) -> None:
        frames = build_set_common_food_frames(
            food,
            device_type=self._device_type,
            mtu=self._mtu,
            scale=scale,
        )
        await self._write_frames(frames)

    async def _write_food_weigh_clear(self) -> None:
        await self._write_common_food(FOOD_WEIGH_CLEAR)
        self._clear_food_weigh_state()
        self._events.emit(Event.FOOD_WEIGH, None)

    async def _sync_food_weigh(self, reading: WeightReading) -> None:
        try:
            async with self._food_weigh_lock:
                food = self._food_weigh
                if food is None:
                    return
                if reading.milligrams == 0:
                    if self._food_weigh_seen_weight:
                        await self._write_food_weigh_clear()
                    return
                if not reading.stable:
                    return
                self._food_weigh_seen_weight = True
                if not self._food_weigh_sent_on_weight:
                    await self._write_common_food(food)
                    self._food_weigh_sent_on_weight = True
        except NotConnectedError:
            return

    async def _rearm_food_weigh(self) -> None:
        try:
            async with self._food_weigh_lock:
                food = self._food_weigh
                if food is None:
                    return
                await self._write_common_food(food)
                self._food_weigh_sent_on_weight = True
        except NotConnectedError:
            return

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
        await self._sync_food_weigh(reading)

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


def _log_dispatch_error(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _LOGGER.exception("notification dispatch failed", exc_info=exc)
