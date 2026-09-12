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
)
from .framing import encode_frame, split_frames
from .nutrition import encode_nutrition_facts


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


def build_set_nutrition_payload(
    food_id: int,
    facts: Sequence[NutritionFact],
    *,
    scale: float | None = None,
) -> bytes:
    """
    Build the inner payload for cmd **213 / 0xD5**.

    Layout: ``foodId u32 BE | count u8 | (type u8 + value u24)…``
    """
    return _write_int_be(food_id) + encode_nutrition_facts(tuple(facts), scale=scale)


def build_set_nutrition_frame(
    food_id: int,
    facts: Sequence[NutritionFact],
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    scale: float | None = None,
) -> bytes:
    """Return one framed **213 / D5** command."""
    payload = build_set_nutrition_payload(food_id, facts, scale=scale)
    return encode_frame(CMD_SET_NUTRITION, payload, device_type=device_type)


def build_common_food_payload(
    food: CommonFood,
    *,
    food_index: int | None = None,
    scale: float | None = None,
) -> bytes:
    """
    Build the inner payload for cmd **214 / D6** or **215 / D7**.

    When ``food_index`` is set, prefix one byte (215 / D7 indexed variant).
    """
    name_bytes = food.name.encode("utf-8")
    body = bytearray()
    if food_index is not None:
        if not 0 <= food_index <= 0xFF:
            msg = f"food_index must fit in one byte, got {food_index}"
            raise ProtocolError(msg)
        body.append(food_index)
    body.extend(_write_int_be(food.food_id))
    body.extend(_write_length_prefixed(name_bytes, field="name"))
    body.extend(_write_length_prefixed(food.icon, field="icon"))
    body.extend(_write_short_be(food.weight))
    if not 0 <= food.magnification <= 0xFF:
        msg = f"magnification must fit in one byte, got {food.magnification}"
        raise ProtocolError(msg)
    body.append(food.magnification)
    body.extend(encode_nutrition_facts(food.facts, scale=scale))
    return bytes(body)


def encode_split_command_frames(
    cmd: int,
    payload: bytes,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
) -> list[bytes]:
    """Split a long payload and wrap each chunk in a General/V2 frame."""
    chunks = split_frames(payload, mtu=mtu)
    return [encode_frame(cmd, chunk, device_type=device_type) for chunk in chunks]


def build_set_common_food_frames(
    food: CommonFood,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    scale: float | None = None,
) -> list[bytes]:
    """Return framed **214 / D6** command(s), split when needed."""
    payload = build_common_food_payload(food, scale=scale)
    return encode_split_command_frames(
        CMD_COMMON_FOOD,
        payload,
        device_type=device_type,
        mtu=mtu,
    )


def build_set_common_food_indexed_frames(
    food_index: int,
    food: CommonFood,
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    mtu: int = DEFAULT_MTU,
    scale: float | None = None,
) -> list[bytes]:
    """Return framed **215 / D7** command(s), split when needed."""
    payload = build_common_food_payload(food, food_index=food_index, scale=scale)
    return encode_split_command_frames(
        CMD_COMMON_FOOD_INDEXED,
        payload,
        device_type=device_type,
        mtu=mtu,
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


def build_delete_common_foods_frame(
    entries: Sequence[FoodReference],
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    use_alt_delete: bool = True,
) -> bytes:
    """
    Return one framed delete command.

    Protocol **113** uses **220 / DC** when ``use_alt_delete`` is true (default).
    """
    cmd = CMD_ALT_DELETE if use_alt_delete else CMD_DELETE_COMMON_FOOD
    payload = build_delete_common_foods_payload(entries)
    return encode_frame(cmd, payload, device_type=device_type)
