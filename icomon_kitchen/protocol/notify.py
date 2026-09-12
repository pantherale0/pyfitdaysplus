"""Parse FFB2 notification payloads."""

from __future__ import annotations

from ..exceptions import ProtocolError
from ..models import Unit, WeightReading
from .constants import NOTIFY_KITCHEN_SCALE_DATA


def parse_weight_notification(payload: bytes) -> WeightReading:
    """
    Parse an ``A6`` kitchen-scale weight notification.

    The Fitdays app exposes field ``b`` as milligrams. Verified live samples
    map cleanly to a 24-bit big-endian milligram field, but the full ``A6``
    field layout is not fully documented yet.
    """
    if len(payload) < 4:
        msg = f"weight notification too short: {len(payload)} bytes"
        raise ProtocolError(msg)
    if payload[0] != NOTIFY_KITCHEN_SCALE_DATA:
        msg = (
            f"expected notify type 0x{NOTIFY_KITCHEN_SCALE_DATA:02x}, "
            f"got 0x{payload[0]:02x}"
        )
        raise ProtocolError(msg)

    milligrams = int.from_bytes(payload[1:4], "big")
    unit = Unit(payload[4]) if len(payload) > 4 else Unit.G
    stable = bool(payload[5]) if len(payload) > 5 else False
    grams = milligrams / 1000.0

    return WeightReading(
        grams=grams,
        milligrams=milligrams,
        unit=unit,
        stable=stable,
        raw_type=payload[0],
        raw_payload=bytes(payload),
    )
