"""Optional voice-related constants (on-device ASR; no BLE audio in v1)."""

from __future__ import annotations

from .models import VOICE_WAKE_PHRASE, DeviceCapabilities, DeviceFunction, FoodInfo

__all__ = [
    "VOICE_WAKE_PHRASE",
    "DeviceCapabilities",
    "DeviceFunction",
    "FoodInfo",
]
