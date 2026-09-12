"""Nutrition fact encoding helpers."""

from __future__ import annotations

from ..exceptions import ProtocolError
from ..models import NutritionFact, NutritionFactType
from .constants import DEFAULT_NUTRITION_SCALE


def encode_nutrition_value_u24(value: int) -> bytes:
    """
    Pack an integer into the native 3-byte big-endian nutrition slot.

    Prefer :func:`encode_nutrition_value` for floats; supply a pre-scaled
    integer here when the wire value is already known from HCI.
    """
    if not 0 <= value <= 0xFFFFFF:
        msg = f"nutrition value must fit in 24 bits, got {value}"
        raise ProtocolError(msg)
    return value.to_bytes(3, "big")


def encode_nutrition_value(
    value: float,
    *,
    scale: float | None = None,
    compact: bool = False,
) -> bytes:
    """
    Encode a float nutrition reading to wire bytes.

    Default scale is :data:`~icomon_kitchen.protocol.constants.DEFAULT_NUTRITION_SCALE`
    (**x100**, verified on live D6: 50 -> 5000). Pass ``scale=1.0`` for raw integers.

    When ``compact`` is true (D6 / D7 common-food bodies), round-2 HCI encodes
    scaled values ``<= 0xFF`` in **2 bytes** (u24 with leading zero byte omitted).
    Values ``> 0xFF`` use **3-byte u24 BE**. Cmd **213 / D5** always uses fixed
    3-byte slots (``compact=False``).
    """
    multiplier = DEFAULT_NUTRITION_SCALE if scale is None else scale
    scaled = round(value * multiplier)
    if not 0 <= scaled <= 0xFFFFFF:
        msg = f"nutrition value must fit in 24 bits, got {scaled}"
        raise ProtocolError(msg)
    if compact and scaled <= 0xFF:
        return scaled.to_bytes(2, "big")
    return scaled.to_bytes(3, "big")


def encode_nutrition_facts(
    facts: tuple[NutritionFact, ...] | list[NutritionFact],
    *,
    scale: float | None = None,
) -> bytes:
    """Return ``count u8 + (type u8 + value u24)…`` for cmd **213 / D5** payloads."""
    if len(facts) > 0xFF:
        msg = f"at most 255 nutrition facts supported, got {len(facts)}"
        raise ProtocolError(msg)
    body = bytearray([len(facts)])
    for fact in facts:
        body.append(int(fact.type))
        body.extend(encode_nutrition_value(fact.value, scale=scale, compact=False))
    return bytes(body)


def encode_nutrition_fact_loop(
    facts: tuple[NutritionFact, ...] | list[NutritionFact],
    *,
    scale: float | None = None,
) -> bytes:
    """Return ``(type u8 + value u24)…`` without a leading count (D6 / D7 body)."""
    body = bytearray()
    for fact in facts:
        body.append(int(fact.type))
        body.extend(encode_nutrition_value(fact.value, scale=scale, compact=True))
    return bytes(body)


def nutrition_fact_type_from_ordinal(ordinal: int) -> NutritionFactType:
    """Return a fact type for a wire ordinal, validating the 0..15 range."""
    if not 0 <= ordinal <= 15:
        msg = f"nutrition fact ordinal must be 0..15, got {ordinal}"
        raise ProtocolError(msg)
    return NutritionFactType(ordinal)
