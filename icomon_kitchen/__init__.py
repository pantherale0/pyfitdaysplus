"""ICOMON Kitchen Scale — async BLE client for Fitdays+ kitchen scales."""

from .client import Client, KitchenScaleClient
from .config import COMM_PROTOCOL, Config
from .device import KitchenScaleDevice
from .exceptions import (
    DeviceNotFoundError,
    IcomonKitchenError,
    NotConnectedError,
    ProtocolError,
    UnsupportedProtocolError,
)
from .models import (
    VOICE_WAKE_PHRASE,
    DeviceCapabilities,
    DeviceFunction,
    FoodInfo,
    ProtocolVersion,
    ScaleInfo,
    ScannedDevice,
    Unit,
    WeightReading,
)
from .protocol.notify import parse_food_info, parse_fun_info

__all__ = [
    "COMM_PROTOCOL",
    "VOICE_WAKE_PHRASE",
    "Client",
    "Config",
    "DeviceCapabilities",
    "DeviceFunction",
    "DeviceNotFoundError",
    "FoodInfo",
    "IcomonKitchenError",
    "KitchenScaleClient",
    "KitchenScaleDevice",
    "NotConnectedError",
    "ProtocolError",
    "ProtocolVersion",
    "ScaleInfo",
    "ScannedDevice",
    "Unit",
    "UnsupportedProtocolError",
    "WeightReading",
    "__version__",
    "parse_food_info",
    "parse_fun_info",
]
__version__ = "0.0.0"
