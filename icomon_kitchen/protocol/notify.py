"""Parse FFB2 notification payloads."""

from __future__ import annotations

from ..exceptions import ProtocolError
from ..models import DeviceCapabilities, FoodInfoNotify, Unit, WeightReading
from .constants import (
    NOTIFY_FOOD_INFO,
    NOTIFY_FUN_INFO,
    NOTIFY_KITCHEN_SCALE_DATA,
    SPLIT_DATA_HEADER_LEN,
)
from .framing import decode_notify_payload


def parse_weight_notification(payload: bytes) -> WeightReading:
    """
    Parse an ``A6`` kitchen-scale weight notification.

    Live FFB2 packets are General/V2 frames whose trailing command is ``0xA6``.
    The inner body is splitData-style ``total_len u16 | seq u8 | data``. Live
    captures place milligrams as a 24-bit big-endian field at data offset 2
    (Fitdays field ``b``). Data byte 0 bit ``0x80`` is treated as unstable.
    Compact ``A6 | mg u24 | unit | stable`` vectors used by tests are still
    accepted.
    """
    notify_type, body = decode_notify_payload(payload)
    if notify_type != NOTIFY_KITCHEN_SCALE_DATA:
        msg = (
            f"expected notify type 0x{NOTIFY_KITCHEN_SCALE_DATA:02x}, "
            f"got 0x{notify_type:02x}"
        )
        raise ProtocolError(msg)
    if _looks_like_split_data(body):
        data = _split_data_fields(body)[1]
        if len(data) < 5:
            msg = f"weight notification too short: {len(data)} data bytes"
            raise ProtocolError(msg)
        milligrams = int.from_bytes(data[2:5], "big")
        unit = Unit.G
        stable = data[0] & 0x80 == 0
    else:
        if len(body) < 3:
            msg = f"weight notification too short: {len(body) + 1} bytes"
            raise ProtocolError(msg)
        milligrams = int.from_bytes(body[0:3], "big")
        unit = _unit_or_grams(body[3]) if len(body) > 3 else Unit.G
        stable = bool(body[4]) if len(body) > 4 else False
    grams = milligrams / 1000.0

    return WeightReading(
        grams=grams,
        milligrams=milligrams,
        unit=unit,
        stable=stable,
        raw_type=notify_type,
        raw_payload=bytes(payload),
    )


def parse_fun_info(payload: bytes) -> DeviceCapabilities:
    """
    Parse a ``funInfo`` (0xA0) notification for device capability bits.

    Live notifies wrap ``0xA0`` as the General/V2 command byte. The vendor SDK
    exposes voice features via ``ICDeviceFunctionVoiceAssistant`` and
    ``ICDeviceFunctionVoiceLanguage``; bit semantics of ``function_flags`` are
    still provisional.
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
        function_flags = int.from_bytes(data[0:4], "big")
    else:
        function_flags = int(data[0])
    return DeviceCapabilities(function_flags=function_flags, raw_payload=bytes(payload))


def parse_food_info_notify(payload: bytes) -> FoodInfoNotify:
    """
    Recognize ``ICFoodInfo`` (notify ``0xAF`` / 175) and preserve raw bytes.

    Fitdays+ decodes this notify in native code before Java sees ``count`` and
    ``foods`` (each with ``foodId`` / ``foodIndex``). Without a verified wire
    map, ``count`` stays ``None`` and ``foods`` is empty — see
    ``protocol.food_info`` for TODO notes.
    """
    notify_type, _body = decode_notify_payload(payload)
    if notify_type != NOTIFY_FOOD_INFO:
        msg = f"expected notify type 0x{NOTIFY_FOOD_INFO:02x}, got 0x{notify_type:02x}"
        raise ProtocolError(msg)

    return FoodInfoNotify(
        raw_type=notify_type,
        raw_payload=bytes(payload),
        count=None,
        foods=(),
    )


def parse_food_info(payload: bytes) -> FoodInfoNotify:
    """Alias for :func:`parse_food_info_notify`."""
    return parse_food_info_notify(payload)


def _looks_like_split_data(body: bytes) -> bool:
    if len(body) < SPLIT_DATA_HEADER_LEN + 1:
        return False
    total_len = int.from_bytes(body[0:2], "big")
    return SPLIT_DATA_HEADER_LEN <= total_len <= len(body) - SPLIT_DATA_HEADER_LEN


def _split_data_fields(body: bytes) -> tuple[int, bytes]:
    total_len = int.from_bytes(body[0:2], "big")
    return body[2], body[3 : 3 + total_len]


def _unit_or_grams(value: int) -> Unit:
    try:
        return Unit(value)
    except ValueError:
        return Unit.G
