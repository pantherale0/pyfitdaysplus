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
    One food entry from an ``ICFoodInfo`` voice selection (SDK map shape).

    Populated when the ``0xAF`` wire layout is known; until then see
    :class:`FoodInfoNotify` which carries ``raw_payload`` only.
    """

    food_id: int
    food_index: int | None = None

    @property
    def foodId(self) -> int:
        """SDK-style alias for :attr:`food_id`."""
        return self.food_id

    @property
    def foodIndex(self) -> int | None:
        """SDK-style alias for :attr:`food_index`."""
        return self.food_index


@dataclass(frozen=True, slots=True)
class FoodInfoNotify:
    """
    Raw ``ICFoodInfo`` notify (``0xAF``) plus decoded fields when available.

    Mirrors the Java map from ``libICBleProtocol.so`` via
    ``ICKitchenScaleGeneralWorker``: ``count``, ``foods``, and ``raw_payload``.
    """

    raw_type: int
    raw_payload: bytes
    count: int | None = None
    foods: tuple[FoodInfo, ...] = ()


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
