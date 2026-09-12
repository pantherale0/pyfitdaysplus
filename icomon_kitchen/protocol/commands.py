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


def build_setting_tare(*, device_type: int = DEVICE_TYPE_KG2458) -> bytes:
    """Build a tare command through the setting path (cmd 210 / 0xD2, type 0)."""
    return encode_frame(CMD_SETTING, b"\x00\x00\x00", device_type=device_type)


def build_setting_unit(
    unit: Unit,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
) -> bytes:
    """Build a unit change command (setting type 2)."""
    payload = bytes([0x02, int(unit), 0x00])
    return encode_frame(CMD_SETTING, payload, device_type=device_type)


def build_setting_weight_grams(
    grams: int,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
) -> bytes:
    """Build a target-weight setting command (setting type 3, u24 BE grams)."""
    if not 0 <= grams <= 0xFFFFFF:
        msg = f"grams must fit in 24 bits, got {grams}"
        raise ValueError(msg)
    payload = bytes([0x03, (grams >> 16) & 0xFF, (grams >> 8) & 0xFF, grams & 0xFF])
    return encode_frame(CMD_SETTING, payload, device_type=device_type)
