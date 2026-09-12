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
    DEVICE_TYPE_KG2458,
)
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
from icomon_kitchen.protocol.nutrition import encode_nutrition_value_u24


def test_encode_nutrition_value_u24() -> None:
    assert encode_nutrition_value_u24(100) == b"\x00\x00\x64"
    assert encode_nutrition_value_u24(0xFFFFFF) == b"\xff\xff\xff"


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
    assert payload.startswith(b"\x00\x00\x00\x07")
    assert b"\x04Oats" in payload  # len + name
    assert b"\x02\x01\x02" in payload  # len + icon
    assert b"\x01\xf4" in payload  # weight 500 u16 BE
    assert payload.endswith(bytes([1, NutritionFactType.PROTEIN, 0, 0, 12]))


def test_common_food_indexed_payload_prefixes_food_index() -> None:
    food = CommonFood(food_id=1, name="A")
    payload = build_common_food_payload(food, food_index=3, scale=1.0)
    assert payload[0] == 3
    assert payload[1:5] == b"\x00\x00\x00\x01"


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
