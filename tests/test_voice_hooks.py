"""Tests for optional voice/food notify hooks on the device."""

from __future__ import annotations

import asyncio

import pytest

from icomon_kitchen.device import KitchenScaleDevice
from icomon_kitchen.models import DeviceFunction


@pytest.mark.asyncio
async def test_device_dispatches_food_and_capability_notifications() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    selections: list[tuple[int, int]] = []
    flags: list[int] = []

    device.set_food_selection_handler(
        lambda food: selections.append((food.food_id, food.food_index))
    )
    device.set_capabilities_handler(lambda caps: flags.append(caps.function_flags))

    voice_flags = int(DeviceFunction.VOICE_ASSISTANT)
    await device._dispatch_notification(bytes([0xAF, 0x00, 0x7B, 0x10]))
    device._handle_capabilities(
        bytes([0xA0, *voice_flags.to_bytes(4, "big")]),
    )

    assert selections == [(0x007B, 0x10)]
    assert flags == [voice_flags]


@pytest.mark.asyncio
async def test_food_selections_iterator_receives_notify() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")

    async def send_food() -> None:
        await device._dispatch_notification(bytes([0xAF, 0x01, 0x2C, 0x00, 0x05]))

    task = asyncio.create_task(send_food())
    food = await device.read_food_selection()
    await task

    assert food.food_id == 0x012C
    assert food.food_index == 0x0005
