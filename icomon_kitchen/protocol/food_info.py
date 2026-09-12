"""
``ICFoodInfo`` (notify ``0xAF``) wire layout notes.

Mapped from Fitdays+ ``ICKitchenScaleGeneralWorker`` / ``ICFoodInfo`` field
names (``foodId``, ``foodIndex``). Offsets follow the same big-endian pattern
as sibling kitchen notifies (``0xA6`` weight, ``0xA0`` funInfo).

Provisional layout
------------------

+---------+------------+------------------------------------------+
| Offset  | Field      | Type                                     |
+=========+============+==========================================+
| 0       | notify     | ``0xAF``                                   |
| 1..2    | foodId     | u16 BE                                   |
| 3..4    | foodIndex  | u16 BE when ``len >= 5``                 |
| 3       | foodIndex  | u8 when ``len == 4`` (compact variant)   |
| 4+ / 5+ | extra      | **TODO** — nutrition / confidence / name |
+---------+------------+------------------------------------------+

On-device voice ASR (wake **"Hello Vita"**) selects a food locally; the client
only receives IDs over BLE — no PCM/audio on FFB2.
"""

from __future__ import annotations

FOOD_INFO_TYPE = 0xAF
FOOD_ID_OFFSET = 1
FOOD_ID_SIZE = 2
FOOD_INDEX_OFFSET_COMPACT = 3
FOOD_INDEX_OFFSET_WIDE = 3
FOOD_INDEX_SIZE_WIDE = 2
MIN_PAYLOAD_FOOD_ID = FOOD_ID_OFFSET + FOOD_ID_SIZE
MIN_PAYLOAD_COMPACT = MIN_PAYLOAD_FOOD_ID + 1
MIN_PAYLOAD_WIDE = FOOD_INDEX_OFFSET_WIDE + FOOD_INDEX_SIZE_WIDE
