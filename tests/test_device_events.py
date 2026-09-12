"""Tests for cached readings and event subscriptions."""

from __future__ import annotations

import asyncio
import logging

import pytest

from icomon_kitchen.device import KitchenScaleDevice
from icomon_kitchen.models import DeviceFunction
from icomon_kitchen.protocol.constants import NOTIFY_FOOD_INFO
from icomon_kitchen.protocol.notify import parse_weight_notification

_WEIGHT_PAYLOAD = bytes([0xA6, 0x02, 0x7C, 0xB8, 0x00, 0x01])


@pytest.mark.asyncio
async def test_weight_cache_updated_on_notify() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")

    assert device.latest_weight is None
    assert device.cached_weight.grams is None

    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    reading = device.latest_weight
    assert reading is not None
    assert reading.milligrams == 163_000
    assert device.cached_weight.grams == reading.grams
    assert device.cached_weight.stable is reading.stable


@pytest.mark.asyncio
async def test_subscribe_weight_receives_callbacks() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    received: list[float] = []

    unsubscribe = device.subscribe_weight(
        lambda reading: received.append(reading.grams),
    )
    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    assert len(received) == 1
    unsubscribe()
    await device._dispatch_notification(_WEIGHT_PAYLOAD)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_multiple_weight_subscribers() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    first: list[int] = []
    second: list[int] = []

    device.subscribe_weight(lambda reading: first.append(reading.milligrams))
    device.subscribe_weight(lambda reading: second.append(reading.milligrams))

    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    assert first == second == [163_000]


@pytest.mark.asyncio
async def test_await_weight_uses_cache_without_waiting() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    reading = await asyncio.wait_for(device.weight, timeout=0.01)
    assert reading.milligrams == 163_000


@pytest.mark.asyncio
async def test_food_selection_cache_and_subscribe() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    payload = bytes([0xAF, 0x01, 0x2C, 0x00, 0x05])
    notifies: list[bytes] = []

    device.subscribe_food_selection(
        lambda notify: notifies.append(notify.raw_payload),
    )
    await device._dispatch_notification(payload)

    assert device.latest_food_selection is not None
    assert device.latest_food_selection.raw_type == NOTIFY_FOOD_INFO
    assert notifies == [payload]


@pytest.mark.asyncio
async def test_capabilities_cache_and_subscribe() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    voice_flags = int(DeviceFunction.VOICE_ASSISTANT)
    flags: list[int] = []

    device.subscribe_capabilities(lambda caps: flags.append(caps.function_flags))
    device._handle_capabilities(bytes([0xA0, *voice_flags.to_bytes(4, "big")]))

    assert device.capabilities is not None
    assert device.capabilities.voice_assistant
    assert flags == [voice_flags]


def test_parse_weight_fixture_used_in_cache_test() -> None:
    reading = parse_weight_notification(_WEIGHT_PAYLOAD)
    assert reading.grams == pytest.approx(163.0)


@pytest.mark.asyncio
async def test_unhandled_notify_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    payload = bytes([0xAC, 0x42, 0x00])
    with caplog.at_level(logging.INFO, logger="icomon_kitchen.device"):
        await device._dispatch_notification(payload)

    assert "unhandled notify type=0xac" in caplog.text
    assert payload.hex() in caplog.text
