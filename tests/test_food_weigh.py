"""Tests for Device food-weigh session (D6 arm / re-arm / clear)."""

from __future__ import annotations

import pytest

from pyfitdaysplus.device import Device
from pyfitdaysplus.events import Event
from pyfitdaysplus.models import FOOD_WEIGH_CLEAR, CommonFood, Unit
from pyfitdaysplus.protocol.food_write import build_set_common_food_frames
from pyfitdaysplus.protocol.framing import encode_frame
from tests.test_gatt import (
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    FakeClient,
    _connect,
    _service,
)

FOOD = CommonFood(food_id=42, name="oats", weight=100)
LIVE_AC_CONFIRM = bytes.fromhex("ac42001100016aa67db6000153d80000043503c389e2ac97")


def _a6_frame(*, milligrams: int = 0, stable: bool = True) -> bytes:
    data = bytearray(14)
    if not stable:
        data[0] = 0x80
    data[1] = int(Unit.G) << 4
    data[2:5] = milligrams.to_bytes(3, "big")
    return encode_frame(0xA6, (14).to_bytes(2, "big") + b"\x00" + bytes(data))


def _d6_frames(client: FakeClient) -> list[bytes]:
    return [frame for _, frame, _ in client.writes if frame[-2] == 0xD6]


def _expected(device: Device, food: CommonFood) -> list[bytes]:
    return build_set_common_food_frames(food, mtu=device._mtu)


async def _connected() -> tuple[Device, FakeClient]:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = await _connect(client)
    return device, client


@pytest.mark.asyncio
async def test_start_food_weigh_sends_d6_not_d5() -> None:
    device, client = await _connected()
    armed: list[CommonFood | None] = []
    device.subscribe(Event.FOOD_WEIGH, armed.append)

    await device.start_food_weigh(FOOD)

    assert device.food_weigh == FOOD
    assert armed == [FOOD]
    assert _d6_frames(client) == _expected(device, FOOD)
    assert all(frame[-2] != 0xD5 for _, frame, _ in client.writes)


@pytest.mark.asyncio
async def test_start_at_zero_then_stable_weight_sends_second_d6() -> None:
    device, client = await _connected()
    await device.start_food_weigh(FOOD)
    await device._dispatch_notification(_a6_frame(milligrams=0))
    assert _d6_frames(client) == _expected(device, FOOD)

    await device._dispatch_notification(_a6_frame(milligrams=88_000))
    assert _d6_frames(client) == _expected(device, FOOD) * 2


@pytest.mark.asyncio
async def test_unstable_weight_does_not_rearm() -> None:
    device, client = await _connected()
    await device.start_food_weigh(FOOD)
    await device._dispatch_notification(_a6_frame(milligrams=88_000, stable=False))
    assert _d6_frames(client) == _expected(device, FOOD)


@pytest.mark.asyncio
async def test_start_with_cached_stable_weight_sends_d6_twice() -> None:
    device, client = await _connected()
    await device._dispatch_notification(_a6_frame(milligrams=88_000))
    await device.start_food_weigh(FOOD)
    assert _d6_frames(client) == _expected(device, FOOD) * 2


@pytest.mark.asyncio
async def test_confirm_rearms_and_zero_clears() -> None:
    device, client = await _connected()
    armed: list[CommonFood | None] = []
    confirms: list[int] = []
    device.subscribe(Event.FOOD_WEIGH, armed.append)
    device.subscribe(
        Event.ON_DEVICE_CONFIRM,
        lambda reading: confirms.append(reading.milligrams),
    )
    await device.start_food_weigh(FOOD)
    await device._dispatch_notification(_a6_frame(milligrams=88_000))
    await device._dispatch_notification(LIVE_AC_CONFIRM)

    assert confirms == [87_000]
    assert device.food_weigh == FOOD
    assert _d6_frames(client) == _expected(device, FOOD) * 3

    await device._dispatch_notification(_a6_frame(milligrams=0))
    assert device.food_weigh is None
    assert armed == [FOOD, None]
    assert _d6_frames(client) == _expected(device, FOOD) * 3 + _expected(
        device, FOOD_WEIGH_CLEAR
    )


@pytest.mark.asyncio
async def test_zero_before_weight_does_not_clear() -> None:
    device, client = await _connected()
    await device.start_food_weigh(FOOD)
    await device._dispatch_notification(_a6_frame(milligrams=0))
    assert device.food_weigh == FOOD
    assert _d6_frames(client) == _expected(device, FOOD)


@pytest.mark.asyncio
async def test_stop_food_weigh_sends_clear() -> None:
    device, client = await _connected()
    await device.start_food_weigh(FOOD)
    await device.stop_food_weigh()
    assert device.food_weigh is None
    assert _d6_frames(client) == _expected(device, FOOD) + _expected(
        device, FOOD_WEIGH_CLEAR
    )


@pytest.mark.asyncio
async def test_history_pull_does_not_rearm() -> None:
    device, client = await _connected()
    await device.start_food_weigh(FOOD)
    before = list(_d6_frames(client))
    device._history_batch = []
    await device._dispatch_notification(LIVE_AC_CONFIRM)
    device._history_batch = None
    assert _d6_frames(client) == before
