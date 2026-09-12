"""Decode common-food write payloads (D6 / D7)."""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ProtocolError
from ..models import CommonFood, NutritionFact
from .constants import COMMON_FOOD_CTRL_BYTE, DEFAULT_NUTRITION_SCALE
from .nutrition import nutrition_fact_type_from_ordinal


@dataclass(frozen=True, slots=True)
class ParsedCommonFood:
    """Decoded fields from a D6 / D7 inner payload."""

    food_id: int
    name: str
    icon: bytes
    weight: int
    magnification: int
    facts: tuple[NutritionFact, ...]
    food_index: int | None = None
    ctrl_byte: int = COMMON_FOOD_CTRL_BYTE

    def to_common_food(self) -> CommonFood:
        """Return a :class:`CommonFood` suitable for re-encoding."""
        return CommonFood(
            food_id=self.food_id,
            name=self.name,
            icon=self.icon,
            weight=self.weight,
            magnification=self.magnification,
            facts=self.facts,
        )


def parse_common_food_payload(payload: bytes) -> ParsedCommonFood:
    """
    Parse the inner D6 / D7 payload (after ``AC 42``, before cmd byte).

    Layout matches round-2 live HCI (see ``docs/kitchen_ble_framing.md``).
    """
    if len(payload) < 8:
        msg = f"common-food payload too short: {len(payload)} bytes"
        raise ProtocolError(msg)

    if payload[6] == COMMON_FOOD_CTRL_BYTE:
        length_value = int.from_bytes(payload[0:2], "big")
        if length_value != len(payload) + 2:
            msg = (
                f"length prefix 0x{length_value:04x} != len(payload)+2 "
                f"(0x{len(payload) + 2:04x})"
            )
            raise ProtocolError(msg)
        return _parse_common_food_body(payload[2:])

    food_index = payload[0]
    length_value = int.from_bytes(payload[1:3], "big")
    if length_value != len(payload) + 1:
        msg = (
            f"indexed length 0x{length_value:04x} != len(payload)+1 "
            f"(0x{len(payload) + 1:04x})"
        )
        raise ProtocolError(msg)
    parsed = _parse_common_food_body(payload[3:])
    return ParsedCommonFood(
        food_id=parsed.food_id,
        name=parsed.name,
        icon=parsed.icon,
        weight=parsed.weight,
        magnification=parsed.magnification,
        facts=parsed.facts,
        food_index=food_index,
        ctrl_byte=parsed.ctrl_byte,
    )


def _parse_common_food_body(body: bytes) -> ParsedCommonFood:
    offset = 0
    if offset + 4 > len(body):
        msg = "common-food body truncated before foodId"
        raise ProtocolError(msg)
    food_id = int.from_bytes(body[offset : offset + 4], "big")
    offset += 4

    ctrl_byte = body[offset]
    if ctrl_byte != COMMON_FOOD_CTRL_BYTE:
        msg = (
            f"expected ctrl byte 0x{COMMON_FOOD_CTRL_BYTE:02x}, "
            f"got 0x{ctrl_byte:02x}"
        )
        raise ProtocolError(msg)
    offset += 1

    if offset >= len(body):
        msg = "common-food body truncated before name_len"
        raise ProtocolError(msg)
    name_len = body[offset]
    offset += 1
    if offset + name_len > len(body):
        msg = "common-food body truncated inside name"
        raise ProtocolError(msg)
    name = body[offset : offset + name_len].decode("utf-8")
    offset += name_len

    if offset >= len(body):
        msg = "common-food body truncated before icon_len"
        raise ProtocolError(msg)
    icon_len = body[offset]
    offset += 1
    if offset + icon_len > len(body):
        msg = "common-food body truncated inside icon"
        raise ProtocolError(msg)
    icon = body[offset : offset + icon_len]
    offset += icon_len

    if offset + 2 > len(body):
        msg = "common-food body truncated before weight"
        raise ProtocolError(msg)
    weight = int.from_bytes(body[offset : offset + 2], "big")
    offset += 2

    if offset >= len(body):
        msg = "common-food body truncated before magnification"
        raise ProtocolError(msg)
    magnification = body[offset]
    offset += 1

    facts = _parse_fact_loop(body[offset:])
    return ParsedCommonFood(
        food_id=food_id,
        name=name,
        icon=icon,
        weight=weight,
        magnification=magnification,
        facts=facts,
        ctrl_byte=ctrl_byte,
    )


def _parse_fact_loop(data: bytes) -> tuple[NutritionFact, ...]:
    facts: list[NutritionFact] = []
    offset = 0
    while offset < len(data):
        if offset + 3 > len(data):
            msg = f"truncated nutrition fact at offset {offset}"
            raise ProtocolError(msg)
        fact_type = nutrition_fact_type_from_ordinal(data[offset])
        offset += 1
        remaining = len(data) - offset
        if remaining == 2:
            wire_value = int.from_bytes(data[offset : offset + 2], "big")
            offset += 2
        elif remaining >= 3:
            wire_value = int.from_bytes(data[offset : offset + 3], "big")
            offset += 3
        else:
            msg = f"incomplete nutrition value at offset {offset}"
            raise ProtocolError(msg)
        facts.append(
            NutritionFact(fact_type, wire_value / DEFAULT_NUTRITION_SCALE)
        )
    return tuple(facts)
