"""Tests for food/nutrition write command encoding."""

from __future__ import annotations

import pytest

from icomon_kitchen.exceptions import ProtocolError
from icomon_kitchen.models import (
    CommonFood,
    FoodReference,
    NutritionFact,
    NutritionFactType,
)
from icomon_kitchen.protocol.constants import (
    CMD_ALT_DELETE,
    CMD_COMMON_FOOD,
    CMD_COMMON_FOOD_INDEXED,
    CMD_SET_NUTRITION,
    COMMON_FOOD_CTRL_BYTE,
    DEFAULT_NUTRITION_SCALE,
    DEVICE_TYPE_KG2458,
)
from icomon_kitchen.protocol.food_decode import parse_common_food_payload
from icomon_kitchen.protocol.food_write import (
    build_common_food_payload,
    build_delete_common_foods_frame,
    build_delete_common_foods_payload,
    build_set_common_food_frames,
    build_set_common_food_indexed_frames,
    build_set_nutrition_frame,
    build_set_nutrition_payload,
)
from icomon_kitchen.protocol.framing import verify_frame
from icomon_kitchen.protocol.nutrition import (
    encode_nutrition_value,
    encode_nutrition_value_u24,
)

LIVE_D6_PRIMARY_HEX = (
    "ac4200260005f6df81097465737420666f6f6400006405000013880100145002001518040020"
    "d6a4"
)
LIVE_D6_CONTINUATION_HEX = "ac42002601d0050015e0d6c7"

LIVE_D6_FOOD = CommonFood(
    food_id=390879,
    name="test food",
    icon=b"",
    weight=100,
    magnification=5,
    facts=(
        NutritionFact(NutritionFactType.CALORIE, 50.0),
        NutritionFact(NutritionFactType.TOTAL_CALORIE, 52.0),
        NutritionFact(NutritionFactType.TOTAL_FAT, 54.0),
        NutritionFact(NutritionFactType.TRANS_FAT, 0.32),
    ),
)


def test_encode_nutrition_value_u24() -> None:
    assert encode_nutrition_value_u24(100) == b"\x00\x00\x64"
    assert encode_nutrition_value_u24(0xFFFFFF) == b"\xff\xff\xff"


def test_default_nutrition_scale_is_100() -> None:
    assert DEFAULT_NUTRITION_SCALE == 100.0
    assert encode_nutrition_value(50.0) == encode_nutrition_value_u24(5000)
    assert encode_nutrition_value(50.0, scale=1.0) == encode_nutrition_value_u24(50)


def test_set_nutrition_payload_structure() -> None:
    facts = [NutritionFact(NutritionFactType.CALORIE, 100.0)]
    payload = build_set_nutrition_payload(0x0000002A, facts, scale=1.0)
    assert payload == b"\x00\x00\x00\x2a\x01\x00" + encode_nutrition_value_u24(100)


def test_set_nutrition_frame_cmd_and_checksum() -> None:
    facts = [NutritionFact(NutritionFactType.SUGAR, 5.0)]
    frame = build_set_nutrition_frame(1, facts, scale=1.0)
    verify_frame(frame)
    assert frame[-2] == CMD_SET_NUTRITION
    assert frame[1] == DEVICE_TYPE_KG2458


def test_live_d6_primary_frame_matches_locked_vector() -> None:
    frame = build_set_common_food_frames(LIVE_D6_FOOD)[0]
    assert frame.hex() == LIVE_D6_PRIMARY_HEX
    verify_frame(frame)


def test_live_d6_primary_round_trips_fields() -> None:
    frame = bytes.fromhex(LIVE_D6_PRIMARY_HEX)
    verify_frame(frame)
    parsed = parse_common_food_payload(frame[2:-2])

    assert parsed.food_id == 390879
    assert parsed.name == "test food"
    assert parsed.icon == b""
    assert parsed.weight == 100
    assert parsed.magnification == 5
    assert parsed.ctrl_byte == COMMON_FOOD_CTRL_BYTE
    assert parsed.food_index is None

    assert len(parsed.facts) == 4
    assert parsed.facts[0] == NutritionFact(NutritionFactType.CALORIE, 50.0)
    assert parsed.facts[1] == NutritionFact(NutritionFactType.TOTAL_CALORIE, 52.0)
    assert parsed.facts[2] == NutritionFact(NutritionFactType.TOTAL_FAT, 54.0)
    assert parsed.facts[3] == NutritionFact(NutritionFactType.TRANS_FAT, 0.32)

    round_trip = build_set_common_food_frames(parsed.to_common_food())[0]
    assert round_trip.hex() == LIVE_D6_PRIMARY_HEX


def test_live_d6_split_continuation_frame() -> None:
    frame = bytes.fromhex(LIVE_D6_CONTINUATION_HEX)
    verify_frame(frame)
    assert frame[-2] == CMD_COMMON_FOOD

    payload = frame[2:-2]
    assert int.from_bytes(payload[0:2], "big") == 0x0026
    assert payload[2] == 0x01
    assert payload[3:] == bytes.fromhex("d0050015e0")


def test_common_food_payload_structure() -> None:
    food = CommonFood(
        food_id=7,
        name="Oats",
        icon=b"\x01\x02",
        weight=500,
        magnification=1,
        facts=(NutritionFact(NutritionFactType.PROTEIN, 12.0),),
    )
    payload = build_common_food_payload(food, scale=1.0)
    assert payload[2:6] == b"\x00\x00\x00\x07"
    assert payload[6] == COMMON_FOOD_CTRL_BYTE
    assert b"\x04Oats" in payload
    assert b"\x02\x01\x02" in payload
    assert b"\x01\xf4" in payload
    assert payload.endswith(bytes([1, NutritionFactType.PROTEIN, 0, 12]))


def test_common_food_indexed_payload_prefixes_food_index() -> None:
    food = CommonFood(food_id=1, name="A")
    payload = build_common_food_payload(food, food_index=3, scale=1.0)
    assert payload[0] == 3
    assert int.from_bytes(payload[3:7], "big") == 1
    assert payload[7] == COMMON_FOOD_CTRL_BYTE


def test_common_food_split_frames_share_cmd() -> None:
    long_name = "x" * 40
    food = CommonFood(food_id=1, name=long_name)
    frames = build_set_common_food_frames(food, mtu=20)
    assert len(frames) > 1
    for frame in frames:
        verify_frame(frame)
        assert frame[-2] == CMD_COMMON_FOOD


def test_common_food_indexed_frames_use_d7() -> None:
    food = CommonFood(food_id=2, name="B")
    frames = build_set_common_food_indexed_frames(4, food)
    assert frames[0][-2] == CMD_COMMON_FOOD_INDEXED


def test_delete_common_foods_payload_structure() -> None:
    entries = [
        FoodReference(food_id=9, food_index=2),
        FoodReference(food_id=10, food_index=0),
    ]
    payload = build_delete_common_foods_payload(entries)
    assert payload == b"\x02\x00\x00\x00\x09\x02\x00\x00\x00\x0a\x00"


def test_delete_common_foods_uses_dc_for_protocol_113() -> None:
    frame = build_delete_common_foods_frame([FoodReference(food_id=1, food_index=0)])
    verify_frame(frame)
    assert frame[-2] == CMD_ALT_DELETE


def test_delete_common_foods_rejects_long_list() -> None:
    entries = [FoodReference(food_id=index, food_index=0) for index in range(256)]
    with pytest.raises(ProtocolError, match="255 delete entries"):
        build_delete_common_foods_payload(entries)
