"""Tests for notify parsing."""

from __future__ import annotations

import pytest

from icomon_kitchen.exceptions import ProtocolError
from icomon_kitchen.models import DeviceFunction, FoodInfo, Unit
from icomon_kitchen.protocol.constants import NOTIFY_FOOD_INFO
from icomon_kitchen.protocol.framing import decode_notify_payload, encode_frame
from icomon_kitchen.protocol.notify import (
    parse_food_info,
    parse_food_info_notify,
    parse_fun_info,
    parse_history_weight_records,
    parse_state_ack,
    parse_weight_event,
    parse_weight_notification,
)

LIVE_A6_IDLE = bytes.fromhex("ac42000e0001000000000000000003c389e200a6e6")
LIVE_A6_WEIGHT = bytes.fromhex("ac42000e000000104be00000000003c389e200a620")
LIVE_A6_UNSTABLE = bytes.fromhex("ac42000e0080000318f80000000003c389e200a678")
# Unit button cycle from a live KG2458 session: G → ML → fl oz → oz → lb → G.
LIVE_A6_UNIT_G = bytes.fromhex("ac42000e0000000877f80000000003c389e200a65c")
LIVE_A6_UNIT_ML = bytes.fromhex("ac42000e0001100000000000000003c389e200a6f6")
LIVE_A6_UNIT_FL_OZ = bytes.fromhex("ac42000e0000600000000000000003c389e200a645")
LIVE_A6_UNIT_OZ = bytes.fromhex("ac42000e000030001f400000000003c389e200a674")
LIVE_A6_UNIT_LB = bytes.fromhex("ac42000e0000200000000000000003c389e200a605")
LIVE_A0_FUN_INFO = bytes.fromhex(
    "ac42001a0000fc4f02262602262600003703e0014b00000001000000000000a008"
)
LIVE_A1_D2_ACK = bytes.fromhex("ac42000200d200a175")
LIVE_A1_EMPTY_ACK = bytes.fromhex("ac420002000000a1a3")


def test_parse_kitchen_scale_weight_milligrams() -> None:
    payload = bytes([0xA6, 0x02, 0x7C, 0xB8, 0x00, 0x01])
    reading = parse_weight_notification(payload)
    assert reading.milligrams == 163_000
    assert reading.grams == pytest.approx(163.0)
    assert reading.unit is Unit.G
    assert reading.stable is True


def test_parse_live_a6_frame_idle_is_zero_grams() -> None:
    reading = parse_weight_notification(LIVE_A6_IDLE)
    assert reading.raw_type == 0xA6
    assert reading.milligrams == 0
    assert reading.stable is True
    assert reading.raw_payload == LIVE_A6_IDLE


def test_parse_live_a6_frame_milligrams() -> None:
    reading = parse_weight_notification(LIVE_A6_WEIGHT)
    assert reading.milligrams == 1_068_000
    assert reading.grams == pytest.approx(1068.0)
    assert reading.unit is Unit.G
    assert reading.stable is True
    assert reading.food_id == 0
    assert reading.user_id == 0x03C389E2


def test_parse_live_a6_frame_unstable_flag() -> None:
    reading = parse_weight_notification(LIVE_A6_UNSTABLE)
    assert reading.milligrams == 203_000
    assert reading.stable is False


def test_parse_live_a6_tick_is_not_on_reading() -> None:
    idle = parse_weight_notification(LIVE_A6_IDLE)
    assert idle.is_tare is False
    assert idle.is_negative is False
    _reading, tick = parse_weight_event(LIVE_A6_IDLE)
    assert tick is False
    negative = parse_weight_notification(LIVE_A6_UNSTABLE)
    assert negative.is_negative is True
    _reading, tick = parse_weight_event(LIVE_A6_UNSTABLE)
    assert tick is False


def test_parse_a6_tick_pressed() -> None:
    data = bytearray(14)
    data[13] = 1
    body = (14).to_bytes(2, "big") + b"\x00" + bytes(data)
    payload = encode_frame(0xA6, body)
    reading, tick = parse_weight_event(payload)
    assert tick is True
    assert reading.milligrams == 0


def test_parse_a6_tare_flag() -> None:
    data = bytearray(14)
    data[0] = 0x40
    body = (14).to_bytes(2, "big") + b"\x00" + bytes(data)
    reading = parse_weight_notification(encode_frame(0xA6, body))
    assert reading.is_tare is True
    assert reading.isTare is True


@pytest.mark.parametrize(
    ("payload", "unit", "milligrams"),
    [
        (LIVE_A6_IDLE, Unit.G, 0),
        (LIVE_A6_UNIT_ML, Unit.ML, 0),
        (LIVE_A6_UNIT_FL_OZ, Unit.FL_OZ_WATER, 0),
        (LIVE_A6_UNIT_OZ, Unit.OZ, 8_000),
        (LIVE_A6_UNIT_LB, Unit.LB, 0),
        (LIVE_A6_UNIT_G, Unit.G, 555_000),
    ],
)
def test_parse_live_a6_frame_unit_nibble(
    payload: bytes, unit: Unit, milligrams: int
) -> None:
    reading = parse_weight_notification(payload)
    assert reading.unit is unit
    assert reading.milligrams == milligrams


def test_parse_live_a6_frame_unit_byte() -> None:
    packed_oz = int(Unit.OZ) << 4
    data = bytes([0x00, packed_oz]) + (28_350).to_bytes(3, "big") + bytes(9)
    body = (14).to_bytes(2, "big") + b"\x00" + data
    reading = parse_weight_notification(encode_frame(0xA6, body))
    assert reading.unit is Unit.OZ
    assert reading.milligrams == 28_350
    assert reading.value == pytest.approx(1.0, rel=1e-3)


def test_weight_reading_converts_grams_to_display_unit() -> None:
    payload = bytes([0xA6, 0x00, 0x01, 0xF4, int(Unit.LB), 0x01])
    reading = parse_weight_notification(payload)
    assert reading.grams == pytest.approx(0.5)
    assert reading.unit is Unit.LB
    assert reading.value == pytest.approx(0.5 / 453.59237)


def test_decode_notify_payload_unwraps_ac_frame() -> None:
    notify_type, inner = decode_notify_payload(LIVE_A6_WEIGHT)
    assert notify_type == 0xA6
    assert inner[:2] == b"\x00\x0e"


def test_parse_live_fun_info_frame() -> None:
    capabilities = parse_fun_info(LIVE_A0_FUN_INFO)
    assert capabilities.raw_payload == LIVE_A0_FUN_INFO
    assert capabilities.function_flags == 0x00FC4F02
    assert capabilities.battery is not None
    assert capabilities.battery.percent == 75
    assert capabilities.battery.battery_type == 2


def test_parse_live_fun_info_battery_varies_by_session() -> None:
    earlier = bytes.fromhex(
        "ac42001a0000fc4f02262602262600003703e0014800000001000000000000a005"
    )
    battery = parse_fun_info(earlier).battery
    assert battery is not None
    assert battery.percent == 72
    assert battery.battery_type == 2


def test_parse_live_a1_d2_ack() -> None:
    ack = parse_state_ack(LIVE_A1_D2_ACK)
    assert ack.command == 0xD2
    assert ack.state == 0
    assert ack.raw_payload == LIVE_A1_D2_ACK


def test_parse_live_a1_empty_cmd() -> None:
    ack = parse_state_ack(LIVE_A1_EMPTY_ACK)
    assert ack.command == 0
    assert ack.state == 0
    with pytest.raises(ProtocolError, match="expected notify type"):
        parse_weight_notification(b"\xa0\x00\x00\x00")


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
        parse_food_info_notify(b"\xa6\x00\x00")


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


LIVE_AC_CONFIRM = bytes.fromhex(
    "ac42001100016aa67db6000153d80000043503c389e2ac97"
)


def test_parse_live_ac_history_confirm() -> None:
    records = parse_history_weight_records(LIVE_AC_CONFIRM)
    assert len(records) == 1
    reading = records[0]
    assert reading.raw_type == 0xAC
    assert reading.milligrams == 87_000
    assert reading.grams == pytest.approx(87.0)
    assert reading.food_id == 1077
    assert reading.user_id == 0x03C389E2
    assert reading.stable is True
