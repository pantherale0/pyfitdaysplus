"""Tests for optional voice/food notify hooks on the device."""

from __future__ import annotations

import asyncio

import pytest

from pyfitdaysplus.device import Device
from pyfitdaysplus.events import Event
from pyfitdaysplus.models import DeviceFunction
from pyfitdaysplus.protocol.constants import NOTIFY_FOOD_INFO


@pytest.mark.asyncio
async def test_device_dispatches_food_and_capability_notifications() -> None:
    device = Device("78:66:A5:D3:47:1E", name="MY_SCALE")
    raw_payloads: list[bytes] = []
    flags: list[int] = []

    device.subscribe(Event.FOOD, lambda notify: raw_payloads.append(notify.raw_payload))
    device.subscribe(Event.CAPABILITIES, lambda caps: flags.append(caps.function_flags))

    payload = bytes([0xAF, 0x00, 0x7B, 0x10])
    voice_flags = int(DeviceFunction.VOICE_ASSISTANT)
    await device._dispatch_notification(payload)
    device._handle_capabilities(
        bytes([0xA0, *voice_flags.to_bytes(4, "big")]),
    )

    assert raw_payloads == [payload]
    assert flags == [voice_flags]


@pytest.mark.asyncio
async def test_food_selections_iterator_receives_notify() -> None:
    device = Device("78:66:A5:D3:47:1E", name="MY_SCALE")
    payload = bytes([0xAF, 0x01, 0x2C, 0x00, 0x05])

    async def send_food() -> None:
        await device._dispatch_notification(payload)

    task = asyncio.create_task(send_food())
    notify = await device.read_food_selection()
    await task

    assert notify.raw_type == NOTIFY_FOOD_INFO
    assert notify.raw_payload == payload
    assert notify.foods == ()
    assert notify.count is None
