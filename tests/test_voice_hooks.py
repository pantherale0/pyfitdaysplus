"""Tests for optional voice/food notify hooks on the device."""

from __future__ import annotations

import pytest

from icomon_kitchen.device import KitchenScaleDevice
from icomon_kitchen.models import DeviceFunction


@pytest.mark.asyncio
async def test_device_dispatches_food_and_capability_notifications() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    foods: list[int | None] = []
    flags: list[int] = []

    device.set_food_info_handler(lambda food: foods.append(food.food_id))
    device.set_capabilities_handler(lambda caps: flags.append(caps.function_flags))

    voice_flags = int(DeviceFunction.VOICE_ASSISTANT)
    await device._dispatch_notification(bytes([0xAF, 0x00, 0x7B, 0xAA]))
    device._handle_capabilities(
        bytes([0xA0, *voice_flags.to_bytes(4, "big")]),
    )

    assert foods == [0x007B]
    assert flags == [voice_flags]
