"""Tests for food/nutrition write command encoding."""

from __future__ import annotations

import pytest

from icomon_kitchen.exceptions import ProtocolError
from icomon_kitchen.models import CommonFood, FoodReference, NutritionFact
from icomon_kitchen.protocol.constants import (
    CMD_ALT_DELETE,
    CMD_COMMON_FOOD,
    CMD_COMMON_FOOD_INDEXED,
    CMD_SET_NUTRITION,
    DEFAULT_NUTRITION_SCALE,
    DEVICE_TYPE_KG2458,
    SET_NUTRITION_SCALE,
)
from icomon_kitchen.protocol.food_decode import (
    parse_common_food_body,
    reassemble_split_data_frames,
)
from icomon_kitchen.protocol.food_write import (
    build_common_food_body,
    build_delete_common_foods_frame,
    build_delete_common_foods_payload,
    build_set_common_food_frames,
    build_set_common_food_indexed_frames,
    build_set_nutrition_frame,
    build_set_nutrition_payload,
    encode_split_data_frames,
)
from icomon_kitchen.protocol.framing import verify_frame
from icomon_kitchen.protocol.nutrition import (
    encode_nutrition_value,
    encode_nutrition_value_u24,
    nutrition_fact_type_from_ordinal,
)

LIVE_D6_FRAME_0_HEX = (
    "ac4200260005f6df81097465737420666f6f6400006405000013880100145002001518040020"
    "d6a4"
)
LIVE_D6_FRAME_1_HEX = "ac42002601d0050015e0d6c7"

LIVE_D6_FOOD = CommonFood(
    food_id=0x05F6DF81,
    name="test food",
    icon=b"",
    weight=100,
    facts=(
        NutritionFact(nutrition_fact_type_from_ordinal(0), 50.0),
        NutritionFact(nutrition_fact_type_from_ordinal(1), 52.0),
        NutritionFact(nutrition_fact_type_from_ordinal(2), 54.0),
        NutritionFact(nutrition_fact_type_from_ordinal(4), 84.0),
        NutritionFact(nutrition_fact_type_from_ordinal(5), 56.0),
    ),
)


def test_encode_nutrition_value_u24() -> None:
    assert encode_nutrition_value_u24(100) == b"\x00\x00\x64"
    assert encode_nutrition_value_u24(0xFFFFFF) == b"\xff\xff\xff"


def test_default_nutrition_scale_is_100() -> None:
    assert DEFAULT_NUTRITION_SCALE == 100.0
    assert SET_NUTRITION_SCALE == 10.0
    assert encode_nutrition_value(50.0) == encode_nutrition_value_u24(5000)
    assert encode_nutrition_value(50.0, scale=1.0) == encode_nutrition_value_u24(50)


def test_set_nutrition_default_scale_is_native_times_ten() -> None:
    facts = [NutritionFact(nutrition_fact_type_from_ordinal(0), 100.0)]
    payload = build_set_nutrition_payload(0x0000002A, facts)
    assert payload == b"\x00\x00\x00\x2a\x01\x00" + encode_nutrition_value_u24(1000)


def test_set_nutrition_payload_structure() -> None:
    facts = [NutritionFact(nutrition_fact_type_from_ordinal(0), 100.0)]
    payload = build_set_nutrition_payload(0x0000002A, facts, scale=1.0)
    assert payload == b"\x00\x00\x00\x2a\x01\x00" + encode_nutrition_value_u24(100)


def test_set_nutrition_frame_uses_split_header() -> None:
    facts = [NutritionFact(nutrition_fact_type_from_ordinal(9), 5.0)]
    frame = build_set_nutrition_frame(1, facts, scale=1.0)
    verify_frame(frame)
    assert frame[-2] == CMD_SET_NUTRITION
    assert frame[1] == DEVICE_TYPE_KG2458
    payload = frame[2:-2]
    assert payload[:3] == b"\x00\x09\x00"
    assert reassemble_split_data_frames([frame]) == b"\x00\x00\x00\x01\x01\x09" + encode_nutrition_value_u24(
        5
    )


def test_live_d6_split_frames_match_locked_hci_pair() -> None:
    frames = build_set_common_food_frames(LIVE_D6_FOOD)
    assert len(frames) == 2
    assert frames[0].hex() == LIVE_D6_FRAME_0_HEX
    assert frames[1].hex() == LIVE_D6_FRAME_1_HEX
    for frame in frames:
        verify_frame(frame)
        assert frame[-2] == CMD_COMMON_FOOD


def test_live_d6_reassembled_payload_round_trips_fields() -> None:
    live_frames = [
        bytes.fromhex(LIVE_D6_FRAME_0_HEX),
        bytes.fromhex(LIVE_D6_FRAME_1_HEX),
    ]
    reassembled = reassemble_split_data_frames(live_frames)
    parsed = parse_common_food_body(reassembled)

    assert parsed.food_id == 0x05F6DF81
    assert parsed.name == "test food"
    assert parsed.icon == b""
    assert parsed.weight == 100
    assert len(parsed.facts) == 5
    assert parsed.facts[0].value == 50.0
    assert int(parsed.facts[0].type) == 0
    assert int(parsed.facts[1].type) == 1
    assert parsed.facts[1].value == 52.0
    assert int(parsed.facts[2].type) == 2
    assert parsed.facts[2].value == 54.0
    assert int(parsed.facts[3].type) == 4
    assert parsed.facts[3].value == 84.0
    assert int(parsed.facts[4].type) == 5
    assert parsed.facts[4].value == 56.0

    encoded = build_set_common_food_frames(parsed.to_common_food())
    assert [frame.hex() for frame in encoded] == [
        LIVE_D6_FRAME_0_HEX,
        LIVE_D6_FRAME_1_HEX,
    ]


def test_common_food_body_layout() -> None:
    food = CommonFood(
        food_id=7,
        name="Oats",
        icon=b"\x01\x02",
        weight=500,
        facts=(NutritionFact(nutrition_fact_type_from_ordinal(10), 12.0),),
    )
    body = build_common_food_body(food, scale=1.0)
    assert body.startswith(b"\x00\x00\x00\x07")
    assert b"\x04Oats" in body
    assert b"\x02\x01\x02" in body
    assert b"\x01\xf4" in body
    assert body.endswith(bytes([1, 10, 0, 0, 12]))


def test_common_food_indexed_payload_prefixes_food_index() -> None:
    food = CommonFood(food_id=1, name="A")
    frames = build_set_common_food_indexed_frames(3, food, scale=1.0)
    body = reassemble_split_data_frames(frames)
    assert body[0] == 3
    assert int.from_bytes(body[1:5], "big") == 1


def test_split_data_single_frame_when_payload_fits() -> None:
    food = CommonFood(food_id=1, name="A")
    body = build_common_food_body(food)
    frames = encode_split_data_frames(CMD_COMMON_FOOD, body)
    assert len(frames) == 1
    assert reassemble_split_data_frames(frames) == body


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


def test_delete_common_foods_uses_dc_split_for_protocol_113() -> None:
    frame = build_delete_common_foods_frame([FoodReference(food_id=1, food_index=0)])
    verify_frame(frame)
    assert frame[-2] == CMD_ALT_DELETE
    assert reassemble_split_data_frames([frame]) == b"\x01\x00\x00\x00\x01\x00"


def test_empty_logical_payload_still_emits_one_split_frame() -> None:
    frames = encode_split_data_frames(CMD_SET_NUTRITION, b"")
    assert len(frames) == 1
    assert reassemble_split_data_frames(frames) == b""


def test_delete_common_foods_rejects_long_list() -> None:
    entries = [FoodReference(food_id=index, food_index=0) for index in range(256)]
    with pytest.raises(ProtocolError, match="255 delete entries"):
        build_delete_common_foods_payload(entries)
