"""Decode common-food write payloads (D6 / D7 splitData)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..exceptions import ProtocolError
from ..models import CommonFood, NutritionFact
from .constants import DEFAULT_NUTRITION_SCALE, SPLIT_DATA_HEADER_LEN
from .nutrition import nutrition_fact_type_from_ordinal


@dataclass(frozen=True, slots=True)
class ParsedCommonFood:
    """Decoded fields from a reassembled D6 / D7 logical payload."""

    food_id: int
    name: str
    icon: bytes
    weight: int
    facts: tuple[NutritionFact, ...]

    def to_common_food(self) -> CommonFood:
        """Return a :class:`CommonFood` suitable for re-encoding."""
        return CommonFood(
            food_id=self.food_id,
            name=self.name,
            icon=self.icon,
            weight=self.weight,
            facts=self.facts,
        )


def reassemble_split_data_frames(frames: Sequence[bytes]) -> bytes:
    """
    Concatenate splitData payload slices from ordered chunk frame bodies.

    Each frame body must be ``total_len u16 BE | seq u8 | slice`` (between
    ``AC 42`` and the trailing cmd byte).
    """
    if not frames:
        msg = "at least one splitData frame is required"
        raise ProtocolError(msg)

    total_len: int | None = None
    slices: dict[int, bytes] = {}
    for frame in frames:
        if len(frame) < 6:
            msg = f"splitData frame too short: {len(frame)} bytes"
            raise ProtocolError(msg)
        body = frame[2:-2]
        if len(body) < SPLIT_DATA_HEADER_LEN:
            msg = "splitData frame body missing header"
            raise ProtocolError(msg)
        frame_total = int.from_bytes(body[0:2], "big")
        sequence = body[2]
        slice_bytes = body[3:]
        if total_len is None:
            total_len = frame_total
        elif frame_total != total_len:
            msg = (
                f"splitData total_len mismatch: 0x{frame_total:04x} != "
                f"0x{total_len:04x}"
            )
            raise ProtocolError(msg)
        if sequence in slices:
            msg = f"duplicate splitData sequence {sequence}"
            raise ProtocolError(msg)
        slices[sequence] = slice_bytes

    if total_len is None:
        msg = "splitData total_len missing"
        raise ProtocolError(msg)

    expected_sequences = range(len(slices))
    if sorted(slices) != list(expected_sequences):
        msg = f"splitData sequences not contiguous: {sorted(slices)}"
        raise ProtocolError(msg)

    reassembled = b"".join(slices[index] for index in expected_sequences)
    if len(reassembled) != total_len:
        msg = f"splitData reassembly length {len(reassembled)} != total_len {total_len}"
        raise ProtocolError(msg)
    return reassembled


def parse_common_food_body(body: bytes) -> ParsedCommonFood:
    """Parse one reassembled D6 logical payload."""
    offset = 0
    if offset + 4 > len(body):
        msg = "common-food body truncated before foodId"
        raise ProtocolError(msg)
    food_id = int.from_bytes(body[offset : offset + 4], "big")
    offset += 4

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

    facts = _parse_counted_facts(body[offset:])
    return ParsedCommonFood(
        food_id=food_id,
        name=name,
        icon=icon,
        weight=weight,
        facts=facts,
    )


def _parse_counted_facts(data: bytes) -> tuple[NutritionFact, ...]:
    if not data:
        msg = "common-food body truncated before fact_count"
        raise ProtocolError(msg)
    count = data[0]
    offset = 1
    facts: list[NutritionFact] = []
    for _ in range(count):
        if offset + 4 > len(data):
            msg = f"truncated nutrition fact at offset {offset}"
            raise ProtocolError(msg)
        fact_type = nutrition_fact_type_from_ordinal(data[offset])
        wire_value = int.from_bytes(data[offset + 1 : offset + 4], "big")
        offset += 4
        facts.append(NutritionFact(fact_type, wire_value / DEFAULT_NUTRITION_SCALE))
    if offset != len(data):
        msg = f"unexpected trailing bytes after facts: {data[offset:].hex()}"
        raise ProtocolError(msg)
    return tuple(facts)
