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
from .models import ProtocolVersion, ScaleInfo, ScannedDevice, Unit, WeightReading

__all__ = [
    "COMM_PROTOCOL",
    "Client",
    "Config",
    "DeviceNotFoundError",
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
]
__version__ = "0.0.0"
