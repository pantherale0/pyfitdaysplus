"""pyfitdaysplus — async BLE client for ICOMON / Fitdays+ kitchen scales."""

from .client import Client, KitchenScaleClient
from .config import COMM_PROTOCOL, Config
from .device import Device, Unsubscribe
from .events import Event
from .exceptions import (
    DeviceNotFoundError,
    IcomonKitchenError,
    NotConnectedError,
    ProtocolError,
)
from .models import (
    VOICE_WAKE_PHRASE,
    BatteryInfo,
    CommandAck,
    CommonFood,
    CompatibilityFlag,
    DeviceCapabilities,
    DeviceFunction,
    FoodInfo,
    FoodInfoNotify,
    FoodReference,
    NutritionFact,
    NutritionFactType,
    ProtocolVersion,
    ScaleInfo,
    ScannedDevice,
    Unit,
    WeightReading,
)
from .protocol.constants import DEFAULT_NUTRITION_SCALE, SET_NUTRITION_SCALE
from .protocol.food_write import (
    build_delete_common_foods_frame,
    build_set_common_food_frames,
    build_set_common_food_indexed_frames,
    build_set_nutrition_frame,
)
from .protocol.notify import parse_food_info_notify, parse_fun_info
from .protocol.nutrition import encode_nutrition_facts, encode_nutrition_value_u24

__all__ = [
    "COMM_PROTOCOL",
    "DEFAULT_NUTRITION_SCALE",
    "SET_NUTRITION_SCALE",
    "VOICE_WAKE_PHRASE",
    "BatteryInfo",
    "Client",
    "CommandAck",
    "CommonFood",
    "CompatibilityFlag",
    "Config",
    "Device",
    "DeviceCapabilities",
    "DeviceFunction",
    "DeviceNotFoundError",
    "Event",
    "FoodInfo",
    "FoodInfoNotify",
    "FoodReference",
    "IcomonKitchenError",
    "KitchenScaleClient",
    "NotConnectedError",
    "NutritionFact",
    "NutritionFactType",
    "ProtocolError",
    "ProtocolVersion",
    "ScaleInfo",
    "ScannedDevice",
    "Unit",
    "Unsubscribe",
    "WeightReading",
    "__version__",
    "build_delete_common_foods_frame",
    "build_set_common_food_frames",
    "build_set_common_food_indexed_frames",
    "build_set_nutrition_frame",
    "encode_nutrition_facts",
    "encode_nutrition_value_u24",
    "parse_food_info_notify",
    "parse_fun_info",
]
__version__ = "0.0.0"
