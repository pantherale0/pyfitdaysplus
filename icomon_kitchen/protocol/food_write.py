"""Encode app→scale food and nutrition write commands."""

from __future__ import annotations

from collections.abc import Sequence

from ..exceptions import ProtocolError
from ..models import CommonFood, FoodReference, NutritionFact
from .constants import (
    CMD_ALT_DELETE,
    CMD_COMMON_FOOD,
    CMD_COMMON_FOOD_INDEXED,
    CMD_DELETE_COMMON_FOOD,
    CMD_SET_NUTRITION,
    DEFAULT_MTU,
    DEVICE_TYPE_KG2458,
    SET_NUTRITION_SCALE,
    SPLIT_DATA_FRAME_BODY_MAX,
    SPLIT_DATA_HEADER_LEN,
)
from .framing import encode_frame
from .nutrition import encode_common_food_facts, encode_nutrition_facts


def _write_int_be(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFFFF:
        msg = f"foodId must fit in u32, got {value}"
        raise ProtocolError(msg)
    return value.to_bytes(4, "big")


def _write_short_be(value: int) -> bytes:
    if not 0 <= value <= 0xFFFF:
        msg = f"weight must fit in u16, got {value}"
        raise ProtocolError(msg)
    return value.to_bytes(2, "big")


def _write_length_prefixed(data: bytes, *, field: str) -> bytes:
    if len(data) > 0xFF:
        msg = f"{field} length must fit in one byte, got {len(data)}"
        raise ProtocolError(msg)
    return bytes([len(data), *data])


def split_data_max_slice(*, frame_body_max: int = SPLIT_DATA_FRAME_BODY_MAX) -> int:
    """Return the maximum payload slice bytes per splitData chunk."""
    return max(frame_body_max - SPLIT_DATA_HEADER_LEN, 1)


def build_set_nutrition_payload(
    food_id: int,
    facts: Sequence[NutritionFact],
    *,
    scale: float | None = None,
) -> bytes:
    """
    Build the inner payload for cmd **213 / 0xD5**.

    Layout: ``foodId u32 BE | count u8 | (type u8 + value u24)…``

    Native D5 scaling is :data:`~icomon_kitchen.protocol.constants.SET_NUTRITION_SCALE`
    (×10). D6/D7 keep ×100.
    """
    multiplier = SET_NUTRITION_SCALE if scale is None else scale
    return _write_int_be(food_id) + encode_nutrition_facts(
        tuple(facts),
        scale=multiplier,
    )


def build_set_nutrition_frames(
    food_id: int,
    facts: Sequence[NutritionFact],
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    scale: float | None = None,
) -> list[bytes]:
    """Return framed **213 / D5** splitData command(s)."""
    payload = build_set_nutrition_payload(food_id, facts, scale=scale)
    return encode_split_data_frames(
        CMD_SET_NUTRITION,
        payload,
        device_type=device_type,
        frame_body_max=mtu,
    )


def build_set_nutrition_frame(
    food_id: int,
    facts: Sequence[NutritionFact],
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    scale: float | None = None,
) -> bytes:
    """Return the first **213 / D5** splitData frame (full set when it fits)."""
    return build_set_nutrition_frames(
        food_id,
        facts,
        device_type=device_type,
        mtu=mtu,
        scale=scale,
    )[0]


def build_common_food_body(
    food: CommonFood,
    *,
    scale: float | None = None,
) -> bytes:
    """
    Build the reassembled D6 / D7 logical payload (before splitData framing).

    Layout: ``foodId u32 | name | icon | weight u16 | fact_count u8 | facts…``
    """
    name_bytes = food.name.encode("utf-8")
    body = bytearray()
    body.extend(_write_int_be(food.food_id))
    body.extend(_write_length_prefixed(name_bytes, field="name"))
    body.extend(_write_length_prefixed(food.icon, field="icon"))
    body.extend(_write_short_be(food.weight))
    body.extend(encode_common_food_facts(food.facts, scale=scale))
    return bytes(body)


def build_common_food_payload(
    food: CommonFood,
    *,
    food_index: int | None = None,
    scale: float | None = None,
) -> bytes:
    """
    Build the full logical payload for **214 / D6** or **215 / D7**.

    For indexed writes, ``food_index u8`` prefixes the body (not split separately).
    """
    body = build_common_food_body(food, scale=scale)
    if food_index is None:
        return body
    if not 0 <= food_index <= 0xFF:
        msg = f"food_index must fit in one byte, got {food_index}"
        raise ProtocolError(msg)
    return bytes([food_index, *body])


def encode_split_data_frames(
    cmd: int,
    logical_payload: bytes,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    frame_body_max: int = SPLIT_DATA_FRAME_BODY_MAX,
) -> list[bytes]:
    """
    Wrap ``logical_payload`` in splitData frames.

    Each frame body: ``total_len u16 BE | seq u8 | payload_slice`` where
    ``total_len`` is the full reassembled logical payload length.
    """
    if len(logical_payload) > 0xFFFF:
        msg = f"logical payload too long for u16 total_len: {len(logical_payload)}"
        raise ProtocolError(msg)

    max_slice = split_data_max_slice(frame_body_max=frame_body_max)
    total_len = len(logical_payload)
    if not logical_payload:
        slices = [b""]
    else:
        slices = [
            logical_payload[index : index + max_slice]
            for index in range(0, len(logical_payload), max_slice)
        ]
    frames: list[bytes] = []
    for sequence, slice_bytes in enumerate(slices):
        if sequence > 0xFF:
            msg = f"splitData sequence overflow at chunk {sequence}"
            raise ProtocolError(msg)
        chunk_payload = total_len.to_bytes(2, "big") + bytes([sequence, *slice_bytes])
        frames.append(encode_frame(cmd, chunk_payload, device_type=device_type))
    return frames


def build_set_common_food_frames(
    food: CommonFood,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    scale: float | None = None,
) -> list[bytes]:
    """Return framed **214 / D6** splitData command(s)."""
    payload = build_common_food_body(food, scale=scale)
    return encode_split_data_frames(
        CMD_COMMON_FOOD,
        payload,
        device_type=device_type,
        frame_body_max=mtu,
    )


def build_set_common_food_indexed_frames(
    food_index: int,
    food: CommonFood,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    scale: float | None = None,
) -> list[bytes]:
    """Return framed **215 / D7** splitData command(s)."""
    payload = build_common_food_payload(food, food_index=food_index, scale=scale)
    return encode_split_data_frames(
        CMD_COMMON_FOOD_INDEXED,
        payload,
        device_type=device_type,
        frame_body_max=mtu,
    )


def build_delete_common_foods_payload(
    entries: Sequence[FoodReference],
) -> bytes:
    """
    Build the inner payload for delete-common-food commands.

    **Provisional layout:** ``count u8 | (foodId u32 BE + foodIndex u8)…``
    """
    if len(entries) > 0xFF:
        msg = f"at most 255 delete entries supported, got {len(entries)}"
        raise ProtocolError(msg)
    body = bytearray([len(entries)])
    for entry in entries:
        if not 0 <= entry.food_index <= 0xFF:
            msg = f"food_index must fit in one byte, got {entry.food_index}"
            raise ProtocolError(msg)
        body.extend(_write_int_be(entry.food_id))
        body.append(entry.food_index)
    return bytes(body)


def build_delete_common_foods_frames(
    entries: Sequence[FoodReference],
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    use_alt_delete: bool = True,
) -> list[bytes]:
    """
    Return framed delete command(s).

    Protocol **113** uses **220 / DC** when ``use_alt_delete`` is true (default).
    """
    cmd = CMD_ALT_DELETE if use_alt_delete else CMD_DELETE_COMMON_FOOD
    payload = build_delete_common_foods_payload(entries)
    return encode_split_data_frames(
        cmd,
        payload,
        device_type=device_type,
        frame_body_max=mtu,
    )


def build_delete_common_foods_frame(
    entries: Sequence[FoodReference],
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    use_alt_delete: bool = True,
) -> bytes:
    """Return the first delete splitData frame (full set when it fits)."""
    return build_delete_common_foods_frames(
        entries,
        device_type=device_type,
        mtu=mtu,
        use_alt_delete=use_alt_delete,
    )[0]
