"""Tests for notify parsing."""

from __future__ import annotations

import pytest

from icomon_kitchen.models import Unit
from icomon_kitchen.protocol.notify import parse_weight_notification


def test_parse_kitchen_scale_weight_milligrams() -> None:
    payload = bytes([0xA6, 0x02, 0x7C, 0xB8, 0x00, 0x01])
    reading = parse_weight_notification(payload)
    assert reading.milligrams == 163_000
    assert reading.grams == pytest.approx(163.0)
    assert reading.unit is Unit.G
    assert reading.stable is True


def test_parse_weight_requires_a6_type() -> None:
    from icomon_kitchen.exceptions import ProtocolError

    with pytest.raises(ProtocolError, match="expected notify type"):
        parse_weight_notification(b"\xA0\x00\x00\x00")
