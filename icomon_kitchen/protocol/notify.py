"""Parse FFB2 notification payloads."""

from __future__ import annotations

from ..exceptions import ProtocolError
from ..models import DeviceCapabilities, FoodInfo, Unit, WeightReading
from .constants import (
    NOTIFY_FOOD_INFO,
    NOTIFY_FUN_INFO,
    NOTIFY_KITCHEN_SCALE_DATA,
)


def parse_weight_notification(payload: bytes) -> WeightReading:
    """
    Parse an ``A6`` kitchen-scale weight notification.

    The Fitdays app exposes field ``b`` as milligrams. Verified live samples
    map cleanly to a 24-bit big-endian milligram field, but the full ``A6``
    field layout is not fully documented yet.
    """
    if len(payload) < 4:
        msg = f"weight notification too short: {len(payload)} bytes"
        raise ProtocolError(msg)
    if payload[0] != NOTIFY_KITCHEN_SCALE_DATA:
        msg = (
            f"expected notify type 0x{NOTIFY_KITCHEN_SCALE_DATA:02x}, "
            f"got 0x{payload[0]:02x}"
        )
        raise ProtocolError(msg)

    milligrams = int.from_bytes(payload[1:4], "big")
    unit = Unit(payload[4]) if len(payload) > 4 else Unit.G
    stable = bool(payload[5]) if len(payload) > 5 else False
    grams = milligrams / 1000.0

    return WeightReading(
        grams=grams,
        milligrams=milligrams,
        unit=unit,
        stable=stable,
        raw_type=payload[0],
        raw_payload=bytes(payload),
    )


def parse_fun_info(payload: bytes) -> DeviceCapabilities:
    """
    Parse a ``funInfo`` (0xA0) notification for device capability bits.

    The vendor SDK exposes voice features via ``ICDeviceFunctionVoiceAssistant``
    and ``ICDeviceFunctionVoiceLanguage``. This parser reads a big-endian
    ``function_flags`` u32 at offset 1 when present; bit semantics are still
    provisional until confirmed against live ``funInfo`` frames.
    """
    if len(payload) < 2:
        msg = f"funInfo notification too short: {len(payload)} bytes"
        raise ProtocolError(msg)
    if payload[0] != NOTIFY_FUN_INFO:
        msg = f"expected notify type 0x{NOTIFY_FUN_INFO:02x}, got 0x{payload[0]:02x}"
        raise ProtocolError(msg)

    function_flags = (
        int.from_bytes(payload[1:5], "big") if len(payload) >= 5 else int(payload[1])
    )
    return DeviceCapabilities(function_flags=function_flags, raw_payload=bytes(payload))


def parse_food_info(payload: bytes) -> FoodInfo:
    """
    Parse an ``ICFoodInfo`` notification (0xAF) after on-device voice recognition.

    Audio stays on the scale; only structured food/nutrition bytes cross BLE.
    Field layout beyond a provisional big-endian ``food_id`` u16 is not fully
    mapped in v1.
    """
    if len(payload) < 2:
        msg = f"foodInfo notification too short: {len(payload)} bytes"
        raise ProtocolError(msg)
    if payload[0] != NOTIFY_FOOD_INFO:
        msg = f"expected notify type 0x{NOTIFY_FOOD_INFO:02x}, got 0x{payload[0]:02x}"
        raise ProtocolError(msg)

    food_id = int.from_bytes(payload[1:3], "big") if len(payload) >= 3 else None
    nutrition_payload = bytes(payload[3:]) if len(payload) > 3 else b""
    return FoodInfo(
        food_id=food_id,
        raw_payload=bytes(payload),
        nutrition_payload=nutrition_payload,
    )
