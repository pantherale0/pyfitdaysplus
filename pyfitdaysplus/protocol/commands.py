"""High-level command builders for General/V2 kitchen scales."""

from __future__ import annotations

from ..models import Unit
from .constants import (
    CMD_APP_REPLY,
    CMD_READ_HISTORY,
    CMD_SETTING,
    DEVICE_TYPE_KG2458,
)
from .framing import encode_frame


def build_app_reply(
    reply_body: bytes = b"\x00\x02\x00\xa0\x00",
    *,
    device_type: int = DEVICE_TYPE_KG2458,
) -> bytes:
    """Build the verified ``app_reply`` frame (cmd 209 / 0xD1)."""
    return encode_frame(CMD_APP_REPLY, reply_body, device_type=device_type)


def build_read_history(*, device_type: int = DEVICE_TYPE_KG2458) -> bytes:
    """Build the short history read frame (cmd 212 / 0xD4)."""
    return encode_frame(CMD_READ_HISTORY, b"\x00\x00\x00", device_type=device_type)


def _setting_body(setting_type: int, param: int) -> bytes:
    """SplitData body used by live D2 writes: ``total_len=2 | seq=0 | type | param``."""
    return bytes([0x00, 0x02, 0x00, setting_type & 0xFF, param & 0xFF])


def build_setting_tare(*, device_type: int = DEVICE_TYPE_KG2458) -> bytes:
    """Build a tare command through the setting path (cmd 210 / 0xD2, type 0)."""
    return encode_frame(CMD_SETTING, _setting_body(0, 0), device_type=device_type)


def build_setting_unit(
    unit: Unit,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
) -> bytes:
    """Build a unit change command (setting type 2)."""
    return encode_frame(
        CMD_SETTING, _setting_body(2, int(unit)), device_type=device_type
    )


def build_setting_confirm(*, device_type: int = DEVICE_TYPE_KG2458) -> bytes:
    """Build a confirm-food command (setting type 10, Fitdays ``confirm food``)."""
    return encode_frame(CMD_SETTING, _setting_body(10, 0), device_type=device_type)


def build_setting_weight_grams(
    grams: int,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
) -> bytes:
    """Build a target-weight setting (type 3) with splitData + u24 BE grams."""
    if not 0 <= grams <= 0xFFFFFF:
        msg = f"grams must fit in 24 bits, got {grams}"
        raise ValueError(msg)
    data = bytes([0x03, (grams >> 16) & 0xFF, (grams >> 8) & 0xFF, grams & 0xFF])
    body = bytes([0x00, len(data), 0x00, *data])
    return encode_frame(CMD_SETTING, body, device_type=device_type)
