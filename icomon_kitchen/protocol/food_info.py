"""
``ICFoodInfo`` (notify ``0xAF`` / 175) — decoded shape vs wire bytes.

Fitdays+ ``ICKitchenScaleGeneralWorker`` receives notify type **175 / 0xAF**
only **after** native ``libICBleProtocol.so`` decodes the BLE bytes into a Map:

- ``count`` (int)
- ``foods`` (list of maps), each with ``foodId`` and ``foodIndex`` (ints)
- Empty ``foods`` when ``count == 0``

Java never sees raw field offsets. The exact BLE payload packing of ``0xAF`` is
**unknown** without native reverse engineering or live HCI of a **Hello Vita**
voice selection.

This library therefore validates the notify type, preserves ``raw_payload``,
and leaves ``count`` / ``foods`` empty until a verified wire map exists.

On-device voice ASR (wake **"Hello Vita"**) runs on the scale; clients receive
food data over BLE, not PCM/audio on FFB2.
"""

from __future__ import annotations

FOOD_INFO_TYPE = 0xAF

# TODO: provisional wire hypotheses (NOT implemented — do not decode yet):
# - leading count byte or u16 BE after 0xAF
# - repeated (foodId, foodIndex) tuples, endianness unknown
# - possible native-only framing before the 0xAF notify type byte on FFB2
