"""Tests for cached readings and event subscriptions."""

from __future__ import annotations

import asyncio
import logging

import pytest

from pyfitdaysplus.device import Device
from pyfitdaysplus.events import Event
from pyfitdaysplus.models import CompatibilityFlag, DeviceFunction, Unit
from pyfitdaysplus.protocol.commands import build_app_reply, build_read_history
from pyfitdaysplus.protocol.constants import NOTIFY_FOOD_INFO
from pyfitdaysplus.protocol.framing import encode_frame
from pyfitdaysplus.protocol.notify import parse_weight_notification
from tests.factories import scale
from tests.test_gatt import (
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    FakeClient,
    _connect,
    _service,
)

_WEIGHT_PAYLOAD = bytes([0xA6, 0x02, 0x7C, 0xB8, 0x00, 0x01])
LIVE_A0 = bytes.fromhex(
    "ac42001a0000fc4f02262602262600003703e0014b00000001000000000000a008"
)
LIVE_AC_CONFIRM = bytes.fromhex("ac42001100016aa67db6000153d80000043503c389e2ac97")


@pytest.mark.asyncio
async def test_weight_cache_updated_on_notify() -> None:
    device = scale()

    assert device.weight is None

    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    reading = device.weight
    assert reading is not None
    assert reading.milligrams == 163_000
    assert reading.grams == pytest.approx(163.0)
    assert reading.stable is True


@pytest.mark.asyncio
async def test_subscribe_weight_receives_callbacks() -> None:
    device = scale()
    received: list[float] = []

    unsubscribe = device.subscribe(
        Event.WEIGHT,
        lambda reading: received.append(reading.grams),
    )
    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    assert len(received) == 1
    unsubscribe()
    await device._dispatch_notification(_WEIGHT_PAYLOAD)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_multiple_weight_subscribers() -> None:
    device = scale()
    first: list[int] = []
    second: list[int] = []

    device.subscribe(Event.WEIGHT, lambda reading: first.append(reading.milligrams))
    device.subscribe(Event.WEIGHT, lambda reading: second.append(reading.milligrams))

    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    assert first == second == [163_000]


@pytest.mark.asyncio
async def test_async_get_weight_uses_cache_without_waiting() -> None:
    device = scale()
    await device._dispatch_notification(_WEIGHT_PAYLOAD)

    reading = await asyncio.wait_for(device.async_get_weight(), timeout=0.01)
    assert reading.milligrams == 163_000


@pytest.mark.asyncio
async def test_food_cache_and_subscribe() -> None:
    device = scale()
    payload = bytes([0xAF, 0x01, 0x2C, 0x00, 0x10, 0x20, 0x30])
    notifies: list[bytes] = []

    device.subscribe(Event.FOOD, lambda notify: notifies.append(notify.raw_payload))
    await device._dispatch_notification(payload)

    assert device.food is not None
    assert device.food.raw_type == NOTIFY_FOOD_INFO
    assert notifies == [payload]


@pytest.mark.asyncio
async def test_capabilities_cache_and_subscribe() -> None:
    device = scale()
    voice_flags = int(DeviceFunction.VOICE_ASSISTANT)
    flags: list[int] = []

    device.subscribe(Event.CAPABILITIES, lambda caps: flags.append(caps.function_flags))
    device._handle_capabilities(bytes([0xA0, *voice_flags.to_bytes(4, "big")]))

    assert device.capabilities is not None
    assert device.capabilities.supports(CompatibilityFlag.VOICE_ASSISTANT)
    assert flags == [voice_flags]


@pytest.mark.asyncio
async def test_subscribe_battery_from_fun_info() -> None:
    device = scale()
    percents: list[int] = []

    device.subscribe(Event.BATTERY, lambda info: percents.append(info.percent))
    device._handle_capabilities(LIVE_A0)

    assert percents == [75]
    assert device.battery is not None
    assert device.battery.percent == 75


def test_parse_weight_fixture_used_in_cache_test() -> None:
    reading = parse_weight_notification(_WEIGHT_PAYLOAD)
    assert reading.grams == pytest.approx(163.0)


@pytest.mark.asyncio
async def test_state_ack_is_parsed_not_unhandled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    device = scale()
    payload = bytes.fromhex("ac42000200d200a175")
    with caplog.at_level(logging.DEBUG, logger="pyfitdaysplus.device"):
        await device._dispatch_notification(payload)

    assert device.ack is not None
    assert device.ack.command == 0xD2
    assert "unhandled notify" not in caplog.text
    assert "ack cmd=0xd2" in caplog.text
    device = scale()
    payload = encode_frame(0xB0, b"\x01")
    with caplog.at_level(logging.DEBUG, logger="pyfitdaysplus.device"):
        await device._dispatch_notification(payload)

    assert "unhandled notify type=0xb0" in caplog.text
    assert payload.hex() in caplog.text


@pytest.mark.asyncio
async def test_live_a6_frame_updates_weight_cache() -> None:
    device = scale()
    payload = bytes.fromhex("ac42000e000000104be00000000003c389e200a620")
    await device._dispatch_notification(payload)

    reading = device.weight
    assert reading is not None
    assert reading.milligrams == 1_068_000
    assert reading.raw_type == 0xA6
    assert reading.unit is Unit.G


@pytest.mark.asyncio
async def test_unit_change_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    device = scale()
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
    with caplog.at_level(logging.DEBUG, logger="pyfitdaysplus.device"):
        await device._dispatch_notification(grams)
        await device._dispatch_notification(ounces)

    assert "unit changed G -> OZ" in caplog.text
    assert device.weight is not None
    assert device.weight.unit is Unit.OZ


def _a6_frame(*, milligrams: int = 1000, is_ok: bool = False) -> bytes:
    data = bytearray(14)
    data[1] = int(Unit.G) << 4
    data[2:5] = milligrams.to_bytes(3, "big")
    if is_ok:
        data[13] = 1
    return encode_frame(0xA6, (14).to_bytes(2, "big") + b"\x00" + bytes(data))


@pytest.mark.asyncio
async def test_subscribe_on_device_confirm_fires_once_per_press() -> None:
    device = scale()
    confirms: list[int] = []
    unsubscribe = device.subscribe(
        Event.ON_DEVICE_CONFIRM,
        lambda reading: confirms.append(reading.milligrams),
    )

    await device._dispatch_notification(_a6_frame(milligrams=250_000))
    await device._dispatch_notification(_a6_frame(milligrams=250_000, is_ok=True))
    await device._dispatch_notification(_a6_frame(milligrams=251_000, is_ok=True))
    await device._dispatch_notification(_a6_frame(milligrams=251_000))
    await device._dispatch_notification(_a6_frame(milligrams=252_000, is_ok=True))

    assert confirms == [250_000, 252_000]
    unsubscribe()
    await device._dispatch_notification(_a6_frame(milligrams=253_000))
    await device._dispatch_notification(_a6_frame(milligrams=253_000, is_ok=True))
    assert confirms == [250_000, 252_000]


@pytest.mark.asyncio
async def test_live_ac_history_fires_on_device_confirm() -> None:
    device = scale()
    confirms: list[tuple[int, int]] = []
    device.subscribe(
        Event.ON_DEVICE_CONFIRM,
        lambda reading: confirms.append((reading.milligrams, reading.food_id)),
    )
    payload = LIVE_AC_CONFIRM
    await device._dispatch_notification(payload)
    assert confirms == [(87_000, 1077)]


def _inject_ac_on_d4(
    client: FakeClient,
    device: Device,
    payloads: list[bytes],
) -> None:
    original_write = client.write_gatt_char
    remaining = list(payloads)

    async def write(uuid: str, data: bytes, response: bool = True) -> None:
        await original_write(uuid, data, response)
        if data[-2] != 0xD4 or not remaining:
            return
        await device._dispatch_notification(remaining.pop(0))

    client.write_gatt_char = write  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_live_ac_acks_with_d1_when_connected() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = await _connect(client)
    confirms: list[int] = []
    device.subscribe(
        Event.ON_DEVICE_CONFIRM,
        lambda reading: confirms.append(reading.milligrams),
    )
    await device._dispatch_notification(LIVE_AC_CONFIRM)
    assert confirms == [87_000]
    assert build_app_reply(notify_type=0xAC) in [frame for _, frame, _ in client.writes]


@pytest.mark.asyncio
async def test_read_history_collects_ac_without_confirm_event() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = await _connect(client)
    confirms: list[int] = []
    dumped: list[int] = []
    device.subscribe(
        Event.ON_DEVICE_CONFIRM,
        lambda reading: confirms.append(reading.milligrams),
    )
    device.subscribe(Event.HISTORY, lambda reading: dumped.append(reading.milligrams))
    _inject_ac_on_d4(client, device, [LIVE_AC_CONFIRM])
    records = await device.read_history(idle_timeout=0.05)

    assert [reading.milligrams for reading in records] == [87_000]
    assert dumped == [87_000]
    assert confirms == []
    assert device.history == records
    assert all(reading.recorded_at is not None for reading in records)
    assert any(frame == build_read_history() for _, frame, _ in client.writes)
    assert build_app_reply(notify_type=0xAC) in [frame for _, frame, _ in client.writes]


@pytest.mark.asyncio
async def test_read_history_paginates_when_page_is_full() -> None:
    client = FakeClient(_service(str(CHAR_WRITE_UUID), str(CHAR_NOTIFY_UUID)))
    device = await _connect(client)
    _inject_ac_on_d4(client, device, [LIVE_AC_CONFIRM])
    records = await device.read_history(idle_timeout=0.05, page_size=1)

    assert [reading.milligrams for reading in records] == [87_000]
    d4_writes = [
        frame for _, frame, _ in client.writes if frame == build_read_history()
    ]
    assert len(d4_writes) == 2
