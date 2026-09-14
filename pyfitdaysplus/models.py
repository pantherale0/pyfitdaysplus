"""Shared data models for kitchen scale interaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, IntFlag


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
    """Vendor ``ICDeviceFunction`` indexes as ``1 << n`` (live A0 ``0x00fc4f02``)."""

    WIFI = 1 << 0
    VOICE_ASSISTANT = 1 << 1
    SOUND_EFFECT = 1 << 2
    VOLUME = 1 << 3
    VOICE_LANGUAGE = 1 << 4
    UPLOAD_BODYFAT = 1 << 5
    WEATHER = 1 << 6
    RESTART = 1 << 7
    FACTORY = 1 << 8
    SERVER_URL = 1 << 9
    NICK_NAME = 1 << 10
    NICK_NAME_IMG = 1 << 11
    SET_UI_ITEM = 1 << 12
    SCALE_LIGHT = 1 << 13
    BABY_MODE = 1 << 14
    HEIGHT_UNIT = 1 << 15
    IMPEDANCE = 1 << 16
    SCAN_WIFI = 1 << 17
    SMART_MODE = 1 << 18
    BATTERY = 1 << 19
    NEW_USER_MANAGER = 1 << 20
    SHOW_USER_INDEX = 1 << 21
    HTTPS_CERTIFICATE = 1 << 22
    WAKE_UP = 1 << 23
    AVATAR = 1 << 24
    HEARTBEAT = 1 << 25
    ECG = 1 << 26
    EIGHT_ELECTRODE = 1 << 32


class CompatibilityFlag(IntFlag):
    """
    Library-facing features for a connected scale.

    Vendor ``funInfo`` bits map onto these; GATT discovery and live notifies
    add the rest. Use ``feature in caps.compatibility`` or ``caps.supports``.
    """

    FUN_INFO = 1 << 0
    WEIGHT = 1 << 1
    WIFI = 1 << 2
    VOICE_ASSISTANT = 1 << 3
    VOICE_LANGUAGE = 1 << 4
    SOUND_EFFECT = 1 << 5
    VOLUME = 1 << 6
    NUTRITION = 1 << 7
    COMMON_FOOD = 1 << 8
    INDEXED_FOOD = 1 << 9
    DELETE_FOOD = 1 << 10
    FILE_TRANSFER = 1 << 11
    OTA_DFU = 1 << 12
    NICK_NAME = 1 << 13
    BABY_MODE = 1 << 14
    BATTERY = 1 << 15
    WAKE_UP = 1 << 16


_FUNCTION_COMPATIBILITY: tuple[tuple[DeviceFunction, CompatibilityFlag], ...] = (
    (DeviceFunction.WIFI, CompatibilityFlag.WIFI),
    (DeviceFunction.VOICE_ASSISTANT, CompatibilityFlag.VOICE_ASSISTANT),
    (DeviceFunction.VOICE_LANGUAGE, CompatibilityFlag.VOICE_LANGUAGE),
    (DeviceFunction.SOUND_EFFECT, CompatibilityFlag.SOUND_EFFECT),
    (DeviceFunction.VOLUME, CompatibilityFlag.VOLUME),
    (DeviceFunction.NICK_NAME, CompatibilityFlag.NICK_NAME),
    (DeviceFunction.BABY_MODE, CompatibilityFlag.BABY_MODE),
    (DeviceFunction.BATTERY, CompatibilityFlag.BATTERY),
    (DeviceFunction.WAKE_UP, CompatibilityFlag.WAKE_UP),
)

# Fitdays+ ``SetKitchenScaleCMD`` gates in ICKitchenScaleGeneralWorker.
_SDK_COMMAND_GATES: tuple[tuple[DeviceFunction, CompatibilityFlag], ...] = (
    (DeviceFunction.VOICE_ASSISTANT, CompatibilityFlag.NUTRITION),
    (DeviceFunction.RESTART, CompatibilityFlag.COMMON_FOOD),
    (DeviceFunction.SOUND_EFFECT, CompatibilityFlag.INDEXED_FOOD),
    (DeviceFunction.SOUND_EFFECT, CompatibilityFlag.DELETE_FOOD),
)

DISCOVERED_COMPATIBILITY = (
    CompatibilityFlag.FUN_INFO
    | CompatibilityFlag.WEIGHT
    | CompatibilityFlag.FILE_TRANSFER
    | CompatibilityFlag.OTA_DFU
)


def compatibility_from_functions(functions: DeviceFunction) -> CompatibilityFlag:
    """Map vendor funInfo bits (and SDK command gates) to library flags."""
    flags = CompatibilityFlag(0)
    for source, dest in (*_FUNCTION_COMPATIBILITY, *_SDK_COMMAND_GATES):
        if functions & source:
            flags |= dest
    return flags


def named_compatibility_flags(
    flags: CompatibilityFlag,
) -> tuple[CompatibilityFlag, ...]:
    """Return each enabled named ``CompatibilityFlag`` member (no composites)."""
    return tuple(
        flag for flag in CompatibilityFlag if flag.value != 0 and flags & flag == flag
    )


VOICE_WAKE_PHRASE = "Hello Vita"


@dataclass(frozen=True, slots=True)
class WeightReading:
    """
    One live weight sample from the scale.

    ``food_id`` is the firmware catalog key on A6 (live KG2458: 1077 → LCD
    “MILK WHOLE”). Treat it as opaque: it is not a UK composition-table code.
    The on-scale default list appears to follow USDA SR NDB numbers (1077 =
    01077 whole milk), whose recipes and macros differ from UK CoFID /
    McCance & Widdowson foods of the same English name.

    History ``0xAC`` records also set ``recorded_at`` from the scale's unix
    timestamp. Live A6 notifies leave it ``None``.
    """

    milligrams: int
    unit: Unit
    stable: bool
    raw_type: int
    raw_payload: bytes
    is_negative: bool = False
    is_tare: bool = False
    food_id: int = 0
    user_id: int = 0
    recorded_at: datetime | None = None

    @property
    def grams(self) -> float:
        """Mass in grams, derived from :attr:`milligrams`."""
        return self.milligrams / 1000.0

    @property
    def value(self) -> float:
        """Numeric value in :attr:`unit` (mass still stored as milligrams)."""
        signed = -self.grams if self.is_negative else self.grams
        return signed / _GRAMS_PER_UNIT[self.unit]


@dataclass(frozen=True, slots=True)
class CommandAck:
    """Parsed ``0xA1`` command acknowledgement from the scale."""

    command: int
    state: int
    raw_payload: bytes


@dataclass(frozen=True, slots=True)
class BatteryInfo:
    """
    Charge reported in ``funInfo`` (``0xA0``).

    Fitdays+ only forwards this when nested ``batteryType`` is 1 or 2 (percent
    or voltage-style). Live KG2458 frames use type 2 and a 0-100 percent byte.
    """

    percent: int
    battery_type: int


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    """Capabilities from ``funInfo`` (0xA0) plus GATT / live discovery."""

    function_flags: DeviceFunction
    compatibility: CompatibilityFlag
    raw_payload: bytes = b""
    battery: BatteryInfo | None = None

    def supports(self, feature: CompatibilityFlag) -> bool:
        """Return whether ``feature`` is enabled."""
        return bool(self.compatibility & feature)

    @property
    def flags(self) -> tuple[CompatibilityFlag, ...]:
        """Enabled named compatibility flags."""
        return named_compatibility_flags(self.compatibility)


@dataclass(frozen=True, slots=True)
class FoodInfo:
    """
    One food entry from an ``ICFoodInfo`` voice selection (SDK map shape).

    One ASR hit from notify ``0xAF``. ``food_index`` is the on-scale slot
    (native writes it before ``foodId``).
    """

    food_id: int
    food_index: int | None = None


@dataclass(frozen=True, slots=True)
class FoodInfoNotify:
    """
    Raw ``ICFoodInfo`` notify (``0xAF``) plus decoded fields when available.

    Mirrors the Java map from ``libICBleProtocol.so``:
    ``count``, ``foods[{foodId, foodIndex}]``, and ``raw_payload``.
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


class NutritionFactType(IntEnum):
    """Fitdays+ ``ICKitchenScaleNutritionFactType`` ordinals (0..15)."""

    CALORIE = 0
    TOTAL_CALORIE = 1
    TOTAL_FAT = 2
    TOTAL_PROTEIN = 3
    TOTAL_CARBOHYDRATE = 4
    TOTAL_FIBER = 5
    TOTAL_CHOLESTEROL = 6
    TOTAL_SODIUM = 7
    TOTAL_SUGAR = 8
    FAT = 9
    PROTEIN = 10
    CARBOHYDRATE = 11
    FIBER = 12
    CHOLESTEROL = 13
    SODIUM = 14
    SUGAR = 15


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
    facts: tuple[NutritionFact, ...] = ()


# Live KG2458 clear after food-weigh: foodId=0, empty name, 100 g, no facts.
FOOD_WEIGH_CLEAR = CommonFood(food_id=0, name="", weight=100, facts=())


@dataclass(frozen=True, slots=True)
class FoodReference:
    """Target entry for ``delete_common_foods``."""

    food_id: int
    food_index: int
