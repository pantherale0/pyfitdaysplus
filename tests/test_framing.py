"""Tests for General/V2 framing and checksum."""

from __future__ import annotations

import pytest

from icomon_kitchen.protocol.commands import (
    build_app_reply,
    build_read_history,
    build_setting_tare,
)
from icomon_kitchen.protocol.framing import checksum, encode_frame, verify_frame


@pytest.mark.parametrize(
    ("frame_hex", "expected_cmd"),
    [
        ("ac42000200a000d173", 0xD1),
        ("ac42000000d4d4", 0xD4),
    ],
)
def test_verified_frame_vectors(frame_hex: str, expected_cmd: int) -> None:
    frame = bytes.fromhex(frame_hex)
    verify_frame(frame)
    assert frame[-2] == expected_cmd


def test_checksum_known_vectors() -> None:
    app_reply = bytes.fromhex("ac42000200a000d173")
    assert checksum(app_reply[2:-1]) == app_reply[-1] == 0x73

    history = bytes.fromhex("ac42000000d4d4")
    assert checksum(history[2:-1]) == history[-1] == 0xD4


def test_build_app_reply_matches_vector() -> None:
    assert build_app_reply().hex() == "ac42000200a000d173"


def test_build_read_history_matches_vector() -> None:
    assert build_read_history().hex() == "ac42000000d4d4"


def test_build_setting_tare_frame() -> None:
    frame = build_setting_tare()
    verify_frame(frame)
    assert frame[-2] == 0xD2
    assert frame[2] == 0x00


def test_encode_frame_rejects_invalid_command() -> None:
    with pytest.raises(Exception, match="command must fit"):
        encode_frame(999)
