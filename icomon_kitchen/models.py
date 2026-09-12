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

    @property
    def symbol(self) -> str:
        """Short label for this unit."""
        return _UNIT_SYMBOLS[self]


_UNIT_SYMBOLS: dict[Unit, str] = {
    Unit.G: "g",
    Unit.ML: "ml",
    Unit.LB: "lb",
    Unit.OZ: "oz",
    Unit.MG: "mg",
    Unit.ML_MILK: "ml milk",
    Unit.FL_OZ_WATER: "fl oz",
    Unit.FL_OZ_MILK: "fl oz milk",
}

# Grams of water-equivalent mass per one display unit.
_GRAMS_PER_UNIT: dict[Unit, float] = {
    Unit.G: 1.0,
    Unit.ML: 1.0,
    Unit.LB: 453.59237,
    Unit.OZ: 28.349523125,
    Unit.MG: 0.001,
    Unit.ML_MILK: 1.03,
    Unit.FL_OZ_WATER: 29.5735295625,
    Unit.FL_OZ_MILK: 30.460735449375,
}


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

    @property
    def value(self) -> float:
        """Numeric value in :attr:`unit` (mass still stored as milligrams)."""
        return self.grams / _GRAMS_PER_UNIT[self.unit]


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


class NutritionFactType(IntEnum):
    """``ICKitchenScaleNutritionFactType`` ordinals (0..15)."""

    CALORIE = 0
    TOTAL_CALORIE = 1
    TOTAL_FAT = 2
    SATURATED_FAT = 3
    TRANS_FAT = 4
    CHOLESTEROL = 5
    SODIUM = 6
    TOTAL_CARBOHYDRATE = 7
    DIETARY_FIBER = 8
    SUGAR = 9
    PROTEIN = 10
    VITAMIN_A = 11
    VITAMIN_C = 12
    CALCIUM = 13
    IRON = 14
    RESERVED = 15


@dataclass(frozen=True, slots=True)
class NutritionFact:
    """One nutrition fact for ``set_nutrition`` / common-food writes."""

    type: NutritionFactType
    value: float


@dataclass(frozen=True, slots=True)
class CommonFood:
    """Custom food payload for ``set_common_food`` / ``set_common_food_indexed``."""

    food_id: int
    name: str
    icon: bytes = b""
    weight: int = 0
    magnification: int = 0  # not sent on D6/D7 wire; kept for app-side use only
    facts: tuple[NutritionFact, ...] = ()


@dataclass(frozen=True, slots=True)
class FoodReference:
    """Target entry for ``delete_common_foods``."""

    food_id: int
    food_index: int

