"""Tests for cached readings and event subscriptions."""

from __future__ import annotations

import asyncio
import logging

import pytest

from icomon_kitchen.device import KitchenScaleDevice
from icomon_kitchen.models import DeviceFunction, Unit
from icomon_kitchen.protocol.constants import NOTIFY_FOOD_INFO
from icomon_kitchen.protocol.framing import encode_frame
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
async def test_state_ack_is_parsed_not_unhandled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    payload = bytes.fromhex("ac42000200d200a175")
    with caplog.at_level(logging.INFO, logger="icomon_kitchen.device"):
        await device._dispatch_notification(payload)

    assert device.latest_ack is not None
    assert device.latest_ack.command == 0xD2
    assert "unhandled notify" not in caplog.text
    assert "ack cmd=0xd2" in caplog.text
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    payload = encode_frame(0xB0, b"\x01")
    with caplog.at_level(logging.INFO, logger="icomon_kitchen.device"):
        await device._dispatch_notification(payload)

    assert "unhandled notify type=0xb0" in caplog.text
    assert payload.hex() in caplog.text


@pytest.mark.asyncio
async def test_live_a6_frame_updates_weight_cache() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    payload = bytes.fromhex("ac42000e000000104be00000000003c389e200a620")
    await device._dispatch_notification(payload)

    reading = device.latest_weight
    assert reading is not None
    assert reading.milligrams == 1_068_000
    assert reading.raw_type == 0xA6
    assert reading.unit is Unit.G
    assert device.cached_weight.unit is Unit.G


@pytest.mark.asyncio
async def test_unit_change_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    grams = encode_frame(
        0xA6,
        (14).to_bytes(2, "big")
        + b"\x00"
        + bytes([0x00, int(Unit.G) << 4])
        + (1000).to_bytes(3, "big")
        + bytes(9),
    )
    ounces = encode_frame(
        0xA6,
        (14).to_bytes(2, "big")
        + b"\x00"
        + bytes([0x00, int(Unit.OZ) << 4])
        + (1000).to_bytes(3, "big")
        + bytes(9),
    )
    with caplog.at_level(logging.INFO, logger="icomon_kitchen.device"):
        await device._dispatch_notification(grams)
        await device._dispatch_notification(ounces)

    assert "unit changed G -> OZ" in caplog.text
    assert device.latest_weight is not None
    assert device.latest_weight.unit is Unit.OZ


def _a6_frame(*, milligrams: int = 1000, tick: bool = False) -> bytes:
    data = bytearray(14)
    data[1] = int(Unit.G) << 4
    data[2:5] = milligrams.to_bytes(3, "big")
    if tick:
        data[13] = 1
    return encode_frame(0xA6, (14).to_bytes(2, "big") + b"\x00" + bytes(data))


@pytest.mark.asyncio
async def test_subscribe_tick_fires_once_per_press() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    ticks: list[int] = []
    unsubscribe = device.subscribe_tick(
        lambda reading: ticks.append(reading.milligrams)
    )

    await device._dispatch_notification(_a6_frame(milligrams=250_000))
    await device._dispatch_notification(_a6_frame(milligrams=250_000, tick=True))
    await device._dispatch_notification(_a6_frame(milligrams=251_000, tick=True))
    await device._dispatch_notification(_a6_frame(milligrams=251_000))
    await device._dispatch_notification(_a6_frame(milligrams=252_000, tick=True))

    assert ticks == [250_000, 252_000]
    unsubscribe()
    await device._dispatch_notification(_a6_frame(milligrams=253_000))
    await device._dispatch_notification(_a6_frame(milligrams=253_000, tick=True))
    assert ticks == [250_000, 252_000]


@pytest.mark.asyncio
async def test_live_ac_history_fires_tick() -> None:
    device = KitchenScaleDevice("78:66:A5:D3:47:1E", name="MY_SCALE")
    ticks: list[tuple[int, int]] = []
    device.subscribe_tick(
        lambda reading: ticks.append((reading.milligrams, reading.food_id))
    )
    payload = bytes.fromhex(
        "ac42001100016aa67db6000153d80000043503c389e2ac97"
    )
    await device._dispatch_notification(payload)
    assert ticks == [(87_000, 1077)]
