"""Shared data models for kitchen scale interaction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
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
