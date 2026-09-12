"""Tests for notify parsing."""

from __future__ import annotations

import pytest

from icomon_kitchen.exceptions import ProtocolError
from icomon_kitchen.models import DeviceFunction, FoodInfo, Unit
from icomon_kitchen.protocol.constants import NOTIFY_FOOD_INFO
from icomon_kitchen.protocol.notify import (
    parse_food_info,
    parse_food_info_notify,
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


def test_parse_food_info_notify_recognizes_af_and_preserves_raw() -> None:
    payload = bytes([0xAF, 0x01, 0x2C, 0x00, 0x10, 0x20, 0x30])
    notify = parse_food_info_notify(payload)
    assert notify.raw_type == NOTIFY_FOOD_INFO
    assert notify.raw_payload == payload
    assert notify.count is None
    assert notify.foods == ()


def test_parse_food_info_alias_matches_notify_parser() -> None:
    payload = bytes([0xAF, 0x00, 0x7B, 0x10])
    assert parse_food_info(payload) == parse_food_info_notify(payload)


def test_parse_food_info_requires_af_type() -> None:
    with pytest.raises(ProtocolError, match="expected notify type"):
        parse_food_info_notify(b"\xA6\x00\x00")


def test_parse_food_info_rejects_empty_payload() -> None:
    with pytest.raises(ProtocolError, match="empty"):
        parse_food_info_notify(b"")


def test_food_info_entry_supports_optional_food_index() -> None:
    entry = FoodInfo(food_id=300, food_index=None)
    assert entry.foodId == 300
    assert entry.foodIndex is None

    indexed = FoodInfo(food_id=300, food_index=16)
    assert indexed.food_index == 16
    assert indexed.foodIndex == 16
