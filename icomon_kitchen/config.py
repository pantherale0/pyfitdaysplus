"""Connection settings for ICOMON Kitchen Scale."""

from __future__ import annotations

from dataclasses import dataclass

from .protocol.constants import (
    DEFAULT_BLE_NAME,
    DEFAULT_MODEL,
    DEFAULT_MTU,
    DEVICE_TYPE_KG2458,
)

COMM_PROTOCOL = "ble"


@dataclass(slots=True)
class Config:
    """BLE and protocol defaults for a kitchen scale."""

    address: str = ""
    ble_name: str = DEFAULT_BLE_NAME
    model: str = DEFAULT_MODEL
    device_type: int = DEVICE_TYPE_KG2458
    mtu: int = DEFAULT_MTU
    scan_timeout: float = 10.0
    app_reply_body: bytes = b"\x00\x02\x00\xa0\x00"
