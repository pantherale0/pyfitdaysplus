"""Protocol constants for KG2458ULB-D / MY_SCALE (GeneralV2, protocol 113)."""

from __future__ import annotations

from uuid import UUID

MAGIC = 0xAC
DEVICE_TYPE_KG2458 = 0x42

SERVICE_UUID = UUID("0000ffb0-0000-1000-8000-00805f9b34fb")
CHAR_WRITE_UUID = UUID("0000ffb1-0000-1000-8000-00805f9b34fb")
CHAR_NOTIFY_UUID = UUID("0000ffb2-0000-1000-8000-00805f9b34fb")
CHAR_FILE_WRITE_UUID = UUID("0000ffb4-0000-1000-8000-00805f9b34fb")
DFU_SERVICE_UUID = UUID("00001530-1212-efde-1523-785feabcd123")

DEFAULT_BLE_NAME = "MY_SCALE"
DEFAULT_MODEL = "KG2458ULB-D"
DEFAULT_MTU = 36  # max splitData frame body (live D6 capture); slice max = MTU - 3

# splitData per-chunk header inside the frame body: total_len u16 + seq u8
SPLIT_DATA_HEADER_LEN = 3
SPLIT_DATA_FRAME_BODY_MAX = DEFAULT_MTU

# Verified on live D6 capture: float nutrition values use round(value * 100) -> u24.
DEFAULT_NUTRITION_SCALE = 100.0
# Native encodeupdateFoodInfo (cmd 213 / D5) multiplies foodValue by 10, not 100.
SET_NUTRITION_SCALE = 10.0

# Java command ids mapped to trailing wire bytes for General/V2 frames.
CMD_APP_REPLY = 209
CMD_SETTING = 210
CMD_READ_HISTORY = 212
CMD_SET_NUTRITION = 213
CMD_COMMON_FOOD = 214
CMD_COMMON_FOOD_INDEXED = 215
CMD_DELETE_COMMON_FOOD = 216
CMD_ALT_DELETE = 220

# Notify package types (first payload byte on FFB2).
NOTIFY_FUN_INFO = 0xA0
NOTIFY_STATE_ACK = 0xA1
NOTIFY_KITCHEN_SCALE_DATA = 0xA6
NOTIFY_HISTORY_WEIGHTS = 0xA9
NOTIFY_HISTORY_WEIGHTS_ALT = 0xAC
NOTIFY_FOOD_INFO = 0xAF
