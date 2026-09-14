"""pyfitdaysplus — async BLE client for ICOMON / Fitdays+ kitchen scales."""

from .config import COMM_PROTOCOL
from .device import Device, Unsubscribe
from .events import Event
from .exceptions import (
    IcomonKitchenError,
    NotConnectedError,
    ProtocolError,
)
from .models import (
    FOOD_WEIGH_CLEAR,
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
    "FOOD_WEIGH_CLEAR",
    "SET_NUTRITION_SCALE",
    "VOICE_WAKE_PHRASE",
    "BatteryInfo",
    "CommandAck",
    "CommonFood",
    "CompatibilityFlag",
    "Device",
    "DeviceCapabilities",
    "DeviceFunction",
    "Event",
    "FoodInfo",
    "FoodInfoNotify",
    "FoodReference",
    "IcomonKitchenError",
    "NotConnectedError",
    "NutritionFact",
    "NutritionFactType",
    "ProtocolError",
    "ProtocolVersion",
    "ScaleInfo",
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
