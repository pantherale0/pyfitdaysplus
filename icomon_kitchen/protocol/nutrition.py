"""Nutrition fact encoding helpers."""

from __future__ import annotations

from ..exceptions import ProtocolError
from ..models import NutritionFact, NutritionFactType


def encode_nutrition_value_u24(value: int) -> bytes:
    """
    Pack an integer into the native 3-byte big-endian nutrition slot.

    The vendor scale applied to ``foodValue`` is **not verified**; callers
    supply a pre-scaled integer when the float mapping is known.
    """
    if not 0 <= value <= 0xFFFFFF:
        msg = f"nutrition value must fit in 24 bits, got {value}"
        raise ProtocolError(msg)
    return value.to_bytes(3, "big")


def encode_nutrition_value(
    value: float,
    *,
    scale: float | None = None,
) -> bytes:
    """
    Encode a float nutrition reading to 3 bytes.

    When ``scale`` is omitted, uses ``round(value)`` (identity scale — **TODO**).
    """
    multiplier = 1.0 if scale is None else scale
    return encode_nutrition_value_u24(round(value * multiplier))


def encode_nutrition_facts(
    facts: tuple[NutritionFact, ...] | list[NutritionFact],
    *,
    scale: float | None = None,
) -> bytes:
    """Return ``count + (type u8 + value u24)…`` for command payloads."""
    if len(facts) > 0xFF:
        msg = f"at most 255 nutrition facts supported, got {len(facts)}"
        raise ProtocolError(msg)
    body = bytearray([len(facts)])
    for fact in facts:
        body.append(int(fact.type))
        body.extend(encode_nutrition_value(fact.value, scale=scale))
    return bytes(body)


def nutrition_fact_type_from_ordinal(ordinal: int) -> NutritionFactType:
    """Return a fact type for a wire ordinal, validating the 0..15 range."""
    if not 0 <= ordinal <= 15:
        msg = f"nutrition fact ordinal must be 0..15, got {ordinal}"
        raise ProtocolError(msg)
    return NutritionFactType(ordinal)
