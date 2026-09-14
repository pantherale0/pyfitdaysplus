"""Parse FFB2 notification payloads."""

from __future__ import annotations

from datetime import UTC, datetime

from ..exceptions import ProtocolError
from ..models import (
    BatteryInfo,
    CommandAck,
    CompatibilityFlag,
    DeviceCapabilities,
    DeviceFunction,
    FoodInfo,
    FoodInfoNotify,
    Unit,
    WeightReading,
    compatibility_from_functions,
)
from .constants import (
    NOTIFY_FOOD_INFO,
    NOTIFY_FUN_INFO,
    NOTIFY_HISTORY_WEIGHTS,
    NOTIFY_HISTORY_WEIGHTS_ALT,
    NOTIFY_KITCHEN_SCALE_DATA,
    NOTIFY_STATE_ACK,
    SPLIT_DATA_HEADER_LEN,
)
from .food_decode import parse_food_reference_list
from .framing import decode_notify_payload


def parse_weight_notification(payload: bytes) -> WeightReading:
    """
    Parse an ``A6`` kitchen-scale weight notification.

    Live FFB2 packets are General/V2 frames whose trailing command is ``0xA6``.
    The inner body is splitData-style ``total_len u16 | seq u8 | data``. Live
    captures place milligrams as a 24-bit big-endian field at data offset 2
    (Fitdays field ``b``). Data byte 0 bit ``0x80`` is treated as unstable.
    Data byte 1 stores the ``ICKitchenScale`` unit ordinal in the high nibble
    (``unit << 4``); a raw 0-7 ordinal is still accepted for compact test
    vectors. Compact ``A6 | mg u24 | unit | stable`` payloads are still
    accepted. Byte 0 bit ``0x40`` is tare. Split-data byte 13 is native
    ``isOk``; that is not stored on :class:`WeightReading`. On KG2458 the
    front-panel ✓ is history ``0xAC`` / ``Event.ON_DEVICE_CONFIRM``.
    """
    reading, _is_ok = parse_weight_event(payload)
    return reading


def parse_weight_event(payload: bytes) -> tuple[WeightReading, bool]:
    """Parse an ``A6`` notify into a reading and whether native ``isOk`` is set."""
    notify_type, body = decode_notify_payload(payload)
    if notify_type != NOTIFY_KITCHEN_SCALE_DATA:
        msg = (
            f"expected notify type 0x{NOTIFY_KITCHEN_SCALE_DATA:02x}, "
            f"got 0x{notify_type:02x}"
        )
        raise ProtocolError(msg)
    is_ok = False
    if _looks_like_split_data(body):
        data = _split_data_fields(body)[1]
        if len(data) < 5:
            msg = f"weight notification too short: {len(data)} data bytes"
            raise ProtocolError(msg)
        milligrams = int.from_bytes(data[2:5], "big")
        unit = _unit_from_notify_byte(data[1])
        flags = data[0]
        stable = flags & 0x80 == 0
        is_negative = flags & 0x80 != 0
        is_tare = flags & 0x40 != 0
        food_id = int.from_bytes(data[5:9], "big") if len(data) >= 9 else 0
        user_id = int.from_bytes(data[9:13], "big") if len(data) >= 13 else 0
        # Native reads ``isOk`` after flags + u32 unit/mg + two u32 fields:
        # 1+4+4+4 = 13, so index 13.
        is_ok = len(data) > 13 and data[13] != 0
    else:
        if len(body) < 3:
            msg = f"weight notification too short: {len(body) + 1} bytes"
            raise ProtocolError(msg)
        milligrams = int.from_bytes(body[0:3], "big")
        unit = _unit_from_notify_byte(body[3]) if len(body) > 3 else Unit.G
        stable = bool(body[4]) if len(body) > 4 else False
        is_negative = False
        is_tare = False
        food_id = 0
        user_id = 0
    reading = WeightReading(
        milligrams=milligrams,
        unit=unit,
        stable=stable,
        raw_type=notify_type,
        raw_payload=bytes(payload),
        is_negative=is_negative,
        is_tare=is_tare,
        food_id=food_id,
        user_id=user_id,
    )
    return reading, is_ok


_HISTORY_RECORD_LEN = 16


def parse_history_weight_records(payload: bytes) -> tuple[WeightReading, ...]:
    """
    Parse ``0xA9`` / ``0xAC`` saved-weight history.

    Live KG2458 confirm (✓) after a named D6 write (2026-09-13):

    ``ac42001100016aa67db6000153d80000043503c389e2ac97``

    splitData ``count u8`` then records of
    ``time u32 BE | flags u8 | mg u24 BE | foodId u32 BE | userId u32 BE``.
    """
    notify_type, body = decode_notify_payload(payload)
    if notify_type not in {NOTIFY_HISTORY_WEIGHTS, NOTIFY_HISTORY_WEIGHTS_ALT}:
        msg = (
            "expected history notify "
            f"0x{NOTIFY_HISTORY_WEIGHTS:02x}/0x{NOTIFY_HISTORY_WEIGHTS_ALT:02x}, "
            f"got 0x{notify_type:02x}"
        )
        raise ProtocolError(msg)
    data = _split_data_fields(body)[1] if _looks_like_split_data(body) else body
    if not data:
        msg = f"history notification too short: {len(payload)} bytes"
        raise ProtocolError(msg)
    count = data[0]
    records_blob = data[1:]
    expected = count * _HISTORY_RECORD_LEN
    if len(records_blob) < expected:
        msg = (
            f"history count={count} needs {expected} record bytes, "
            f"got {len(records_blob)}"
        )
        raise ProtocolError(msg)
    readings: list[WeightReading] = []
    for index in range(count):
        start = index * _HISTORY_RECORD_LEN
        record = records_blob[start : start + _HISTORY_RECORD_LEN]
        flags = record[4]
        milligrams = int.from_bytes(record[5:8], "big")
        food_id = int.from_bytes(record[8:12], "big")
        user_id = int.from_bytes(record[12:16], "big")
        recorded_at = datetime.fromtimestamp(
            int.from_bytes(record[0:4], "big"),
            tz=UTC,
        )
        readings.append(
            WeightReading(
                milligrams=milligrams,
                unit=Unit.G,
                stable=True,
                raw_type=notify_type,
                raw_payload=bytes(payload),
                is_negative=flags & 0x80 != 0,
                is_tare=flags & 0x40 != 0,
                food_id=food_id,
                user_id=user_id,
                recorded_at=recorded_at,
            )
        )
    return tuple(readings)


def parse_state_ack(payload: bytes) -> CommandAck:
    """
    Parse an ``A1`` command acknowledgement.

    Live D2 ACK: ``ac42000200d200a175`` → ``cmd=0xD2``, ``state=0``.
    Inner body is splitData ``total_len=2 | seq | cmd | state``.
    """
    notify_type, body = decode_notify_payload(payload)
    if notify_type != NOTIFY_STATE_ACK:
        msg = f"expected notify type 0x{NOTIFY_STATE_ACK:02x}, got 0x{notify_type:02x}"
        raise ProtocolError(msg)
    if len(body) >= 5 and int.from_bytes(body[0:2], "big") == 2:
        return CommandAck(command=body[3], state=body[4], raw_payload=bytes(payload))
    if len(body) >= 2:
        return CommandAck(command=body[0], state=body[1], raw_payload=bytes(payload))
    msg = f"state ack too short: {len(body)} bytes"
    raise ProtocolError(msg)


def parse_fun_info(payload: bytes) -> DeviceCapabilities:
    """
    Parse a ``funInfo`` (0xA0) notification for device capability bits.

    Live notifies wrap ``0xA0`` as the General/V2 command byte. Native
    ``decodedeviceInfoData`` treats the first u32 as packed capability bits
    (``ICDeviceFunction`` indexes, including VoiceLanguage at bit 4) and later
    bytes as unit precisions (``divG`` / ``divOZ`` / …), ``batteryType``, and
    ``battery``. This helper keeps the u32 as ``function_flags`` and reads
    charge at offset 15.
    """
    notify_type, body = decode_notify_payload(payload)
    if notify_type != NOTIFY_FUN_INFO:
        msg = f"expected notify type 0x{NOTIFY_FUN_INFO:02x}, got 0x{notify_type:02x}"
        raise ProtocolError(msg)
    data = _split_data_fields(body)[1] if _looks_like_split_data(body) else body
    if not data:
        msg = f"funInfo notification too short: {len(payload)} bytes"
        raise ProtocolError(msg)
    if len(data) >= 4:
        function_flags = DeviceFunction(int.from_bytes(data[0:4], "big"))
    else:
        function_flags = DeviceFunction(int(data[0]))
    return DeviceCapabilities(
        function_flags=function_flags,
        compatibility=(
            compatibility_from_functions(function_flags) | CompatibilityFlag.FUN_INFO
        ),
        raw_payload=bytes(payload),
        battery=_battery_from_fun_info(data),
    )


def _battery_from_fun_info(data: bytes) -> BatteryInfo | None:
    """
    Read charge from a kitchen ``decodedeviceInfoData`` payload.

    Native codec: ``batteryType`` is bits 8-9 of the second u32; ``battery`` is
    the second integer read after ``supportDataTypes`` / ``funInfo2``. On live
    26-byte KG2458 frames that percent sits at offset 15 (sessions at 72% and
    75% differed only in this byte).
    """
    if len(data) < 16:
        return None
    packed = int.from_bytes(data[4:8], "big") if len(data) >= 8 else 0
    battery_type = (packed >> 8) & 0x3
    percent = data[15]
    if percent > 100:
        return None
    return BatteryInfo(percent=percent, battery_type=battery_type)


def parse_food_info_notify(payload: bytes) -> FoodInfoNotify:
    """
    Parse ``ICFoodInfo`` (notify ``0xAF`` / 175).

    After optional splitData unwrap, native kitchen 42 reads
    ``count u8`` then ``foodIndex u8`` + ``foodId u32 BE`` per entry (same
    packing as delete D8/DC). Java still presents ``foods[{foodId, foodIndex}]``.
    """
    notify_type, body = decode_notify_payload(payload)
    if notify_type != NOTIFY_FOOD_INFO:
        msg = f"expected notify type 0x{NOTIFY_FOOD_INFO:02x}, got 0x{notify_type:02x}"
        raise ProtocolError(msg)
    data = _split_data_fields(body)[1] if _looks_like_split_data(body) else body
    entries = parse_food_reference_list(data)
    foods = tuple(
        FoodInfo(food_id=entry.food_id, food_index=entry.food_index)
        for entry in entries
    )
    return FoodInfoNotify(
        raw_type=notify_type,
        raw_payload=bytes(payload),
        count=len(foods),
        foods=foods,
    )


def _looks_like_split_data(body: bytes) -> bool:
    if len(body) < SPLIT_DATA_HEADER_LEN + 1:
        return False
    total_len = int.from_bytes(body[0:2], "big")
    return SPLIT_DATA_HEADER_LEN <= total_len <= len(body) - SPLIT_DATA_HEADER_LEN


def _split_data_fields(body: bytes) -> tuple[int, bytes]:
    total_len = int.from_bytes(body[0:2], "big")
    return body[2], body[3 : 3 + total_len]


def _unit_from_notify_byte(value: int) -> Unit:
    """Decode a live packed unit byte or a compact raw ordinal."""
    try:
        return Unit(value)
    except ValueError:
        pass
    try:
        return Unit(value >> 4)
    except ValueError:
        return Unit.G
