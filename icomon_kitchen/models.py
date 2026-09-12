"""Shared data models for kitchen scale interaction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Literal


class Unit(IntEnum):
    """Display/weighing units supported by protocol 113 kitchen scales."""

    G = 0
    ML = 1
    LB = 2
    OZ = 3
    MG = 4
    ML_MILK = 5
    FL_OZ_WATER = 6
    FL_OZ_MILK = 7


class ProtocolVersion(IntEnum):
    """Known ICOMON scale protocol families."""

    LEGACY_110 = 110
    LEGACY_111 = 111
    GENERAL_V2_113 = 113


class DeviceFunction(IntFlag):
    """
    Named bits from ``ICConstant.ICDeviceFunction`` (vendor SDK).

    Bit positions are **not verified on the wire** yet; treat ``function_flags``
    on :class:`DeviceCapabilities` as authoritative and use these names only as
    helpers once offsets are confirmed against ``funInfo`` captures.
    """

    VOICE_ASSISTANT = 1 << 12
    VOICE_LANGUAGE = 1 << 13


VOICE_WAKE_PHRASE = "Hello Vita"


@dataclass(frozen=True, slots=True)
class ScannedDevice:
    """A BLE scale discovered during scanning."""

    name: str
    address: str
    rssi: int | None = None


@dataclass(frozen=True, slots=True)
class WeightReading:
    """One live weight sample from the scale."""

    grams: float
    milligrams: int
    unit: Unit
    stable: bool
    raw_type: int
    raw_payload: bytes


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    """Capabilities reported in a ``funInfo`` (0xA0) notification."""

    function_flags: int
    raw_payload: bytes

    def supports(self, function: DeviceFunction) -> bool:
        """Return whether ``function`` appears enabled in ``function_flags``."""
        return bool(self.function_flags & function)

    @property
    def voice_assistant(self) -> bool:
        """Return whether the scale reports on-device voice ASR."""
        return self.supports(DeviceFunction.VOICE_ASSISTANT)

    @property
    def voice_language(self) -> bool:
        """Configurable voice language (SDK: ``ICDeviceFunctionVoiceLanguage``)."""
        return self.supports(DeviceFunction.VOICE_LANGUAGE)


@dataclass(frozen=True, slots=True)
class FoodInfo:
    """
    Food/nutrition payload from on-device voice ASR (``ICFoodInfo``, notify 0xAF).

    Recognition runs on the scale microphone; Fitdays+ receives structured food
    data over BLE. This v1 parser exposes a best-effort ``food_id`` plus the
    raw tail for forward-compatible decoding.
    """

    food_id: int | None
    raw_payload: bytes
    nutrition_payload: bytes


@dataclass(frozen=True, slots=True)
class ScaleInfo:
    """Static information about a connected kitchen scale."""

    model: str
    ble_name: str
    address: str
    device_type: int
    protocol: ProtocolVersion
    firmware: str | None = None
    hardware: str | None = None


SettingKind = Literal["tare", "power", "unit", "weight"]
