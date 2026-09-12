"""Tests for notify parsing."""

from __future__ import annotations

import pytest

from icomon_kitchen.exceptions import ProtocolError
from icomon_kitchen.models import DeviceFunction, Unit
from icomon_kitchen.protocol.notify import (
    parse_food_info,
    parse_fun_info,
    parse_weight_notification,
)


def test_parse_kitchen_scale_weight_milligrams() -> None:
    payload = bytes([0xA6, 0x02, 0x7C, 0xB8, 0x00, 0x01])
    reading = parse_weight_notification(payload)
    assert reading.milligrams == 163_000
    assert reading.grams == pytest.approx(163.0)
    assert reading.unit is Unit.G
    assert reading.stable is True


def test_parse_weight_requires_a6_type() -> None:
    with pytest.raises(ProtocolError, match="expected notify type"):
        parse_weight_notification(b"\xA0\x00\x00\x00")


def test_parse_fun_info_voice_capability_bits() -> None:
    flags = int(DeviceFunction.VOICE_ASSISTANT | DeviceFunction.VOICE_LANGUAGE)
    payload = bytes([0xA0, *flags.to_bytes(4, "big"), 0x00])
    capabilities = parse_fun_info(payload)
    assert capabilities.voice_assistant is True
    assert capabilities.voice_language is True
    assert capabilities.supports(DeviceFunction.VOICE_ASSISTANT)


def test_parse_food_info_wide_layout() -> None:
    payload = bytes([0xAF, 0x01, 0x2C, 0x00, 0x10, 0x20, 0x30])
    food = parse_food_info(payload)
    assert food.food_id == 0x012C
    assert food.food_index == 0x0010
    assert food.foodId == food.food_id
    assert food.foodIndex == food.food_index
    assert food.extra == b"\x20\x30"
    assert food.raw_payload == payload


def test_parse_food_info_compact_layout() -> None:
    payload = bytes([0xAF, 0x00, 0x7B, 0x10])
    food = parse_food_info(payload)
    assert food.food_id == 0x007B
    assert food.food_index == 0x10
    assert food.extra == b""


def test_parse_food_info_requires_af_type() -> None:
    with pytest.raises(ProtocolError, match="expected notify type"):
        parse_food_info(b"\xA6\x00\x00")


def test_parse_food_info_requires_food_index_byte() -> None:
    with pytest.raises(ProtocolError, match="too short for foodIndex"):
        parse_food_info(b"\xAF\x01\x2C")
