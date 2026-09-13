"""General/V2 frame encoding and checksum helpers."""

from __future__ import annotations

from ..exceptions import ProtocolError
from .constants import DEVICE_TYPE_KG2458, MAGIC


def checksum(body: bytes) -> int:
    """Return the 8-bit additive checksum for bytes starting at index 2."""
    return sum(body) & 0xFF


def encode_frame(
    cmd: int,
    payload: bytes = b"",
    *,
    device_type: int = DEVICE_TYPE_KG2458,
    pad_to_mtu: int | None = None,
) -> bytes:
    """
    Build one General/V2 frame.

    Layout: ``AC | device_type | payload... | cmd | checksum`` where the
    checksum covers every byte from index 2 through ``len-2`` inclusive.

    Short commands use a compact frame (see verified ``ac42…`` vectors). When
    ``pad_to_mtu`` is set, zero bytes are inserted before the command byte so
    the frame grows toward the ATT MTU for larger payloads.
    """
    if not 0 <= cmd <= 0xFF:
        msg = f"command must fit in one byte, got {cmd}"
        raise ProtocolError(msg)

    body = bytearray(payload)
    if pad_to_mtu is not None:
        target_inner = max(len(payload) + 1, pad_to_mtu - 2)
        if target_inner < len(payload) + 1:
            msg = "pad_to_mtu is too small for payload and command byte"
            raise ProtocolError(msg)
        body.extend(b"\x00" * (target_inner - len(payload) - 1))
    body.append(cmd & 0xFF)

    frame = bytes([MAGIC, device_type, *body])
    cs = checksum(frame[2:])
    return frame + bytes([cs])


def verify_frame(frame: bytes) -> None:
    """Validate magic, length, and checksum."""
    if len(frame) < 4:
        msg = f"frame too short: {len(frame)} bytes"
        raise ProtocolError(msg)
    if frame[0] != MAGIC:
        msg = f"invalid magic 0x{frame[0]:02x}, expected 0x{MAGIC:02x}"
        raise ProtocolError(msg)
    expected = checksum(frame[2:-1])
    if frame[-1] != expected:
        msg = f"checksum mismatch: got 0x{frame[-1]:02x}, expected 0x{expected:02x}"
        raise ProtocolError(msg)


def split_frames(data: bytes, *, mtu: int = 20) -> list[bytes]:
    """Split a long payload into MTU-sized chunks for protocol 113."""
    chunk_size = max(mtu - 7, 1)
    return [
        data[index : index + chunk_size] for index in range(0, len(data), chunk_size)
    ]


def encode_file_frame(data: bytes) -> bytes:
    """Return raw bytes for FFB4 file transfer (no AC/checksum wrapper)."""
    return data


def decode_frame(frame: bytes) -> tuple[int, int, bytes]:
    """
    Return ``(device_type, command, payload)`` from a General/V2 frame.

    Layout: ``AC | device_type | payload… | cmd | checksum``.
    """
    verify_frame(frame)
    return frame[1], frame[-2], frame[2:-2]


def decode_notify_payload(payload: bytes) -> tuple[int, bytes]:
    """
    Return ``(notify_type, inner_payload)`` from a raw FFB2 packet.

    Live KG2458 notifies are General/V2 frames (magic ``AC``, command before
    checksum). Compact test vectors start with the notify type byte itself.
    """
    if not payload:
        msg = "empty notify"
        raise ProtocolError(msg)
    if payload[0] == MAGIC:
        _device_type, command, inner = decode_frame(payload)
        return command, inner
    return payload[0], payload[1:]
