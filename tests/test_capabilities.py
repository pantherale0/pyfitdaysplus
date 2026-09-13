"""Compatibility flags derived from funInfo and GATT discovery."""

from __future__ import annotations

import pytest

from pyfitdaysplus.device import Device
from pyfitdaysplus.models import (
    CompatibilityFlag,
    DeviceFunction,
    compatibility_from_functions,
    named_compatibility_flags,
)
from pyfitdaysplus.protocol.constants import DFU_SERVICE_UUID
from pyfitdaysplus.protocol.notify import parse_fun_info

LIVE_A0 = bytes.fromhex(
    "ac42001a0000fc4f02262602262600003703e0014b00000001000000000000a008"
)


def test_live_fun_info_maps_nutrition_not_common_food() -> None:
    caps = parse_fun_info(LIVE_A0)
    assert CompatibilityFlag.FUN_INFO in caps.compatibility
    assert CompatibilityFlag.VOICE_ASSISTANT in caps.compatibility
    assert CompatibilityFlag.NUTRITION in caps.compatibility
    assert CompatibilityFlag.WAKE_UP in caps.compatibility
    assert CompatibilityFlag.WIFI not in caps.compatibility
    assert CompatibilityFlag.COMMON_FOOD not in caps.compatibility
    assert CompatibilityFlag.INDEXED_FOOD not in caps.compatibility
    assert caps.supports(CompatibilityFlag.NUTRITION)
    assert not (caps.function_flags & DeviceFunction.RESTART)
    names = {flag.name for flag in caps.flags}
    assert "NUTRITION" in names
    assert "COMMON_FOOD" not in names


def test_restart_bit_enables_common_food_gate() -> None:
    flags = compatibility_from_functions(DeviceFunction.RESTART)
    assert CompatibilityFlag.COMMON_FOOD in flags
    assert CompatibilityFlag.NUTRITION not in flags


def test_sound_effect_enables_indexed_and_delete_food() -> None:
    flags = compatibility_from_functions(DeviceFunction.SOUND_EFFECT)
    assert CompatibilityFlag.INDEXED_FOOD in flags
    assert CompatibilityFlag.DELETE_FOOD in flags


def test_named_flags_skip_zero() -> None:
    combined = CompatibilityFlag.WEIGHT | CompatibilityFlag.OTA_DFU
    assert named_compatibility_flags(combined) == (
        CompatibilityFlag.WEIGHT,
        CompatibilityFlag.OTA_DFU,
    )


def test_merge_discovered_is_idempotent() -> None:
    device = Device("78:66:A5:D3:47:1E", name="MY_SCALE")
    device._merge_discovered(CompatibilityFlag.WEIGHT)
    first = device.capabilities
    device._merge_discovered(CompatibilityFlag.WEIGHT)
    assert device.capabilities is first
    device._merge_discovered(CompatibilityFlag.OTA_DFU)
    assert device.capabilities is not None
    assert CompatibilityFlag.OTA_DFU in device.capabilities.compatibility
    assert CompatibilityFlag.WEIGHT in device.capabilities.compatibility


def test_fun_info_keeps_weight_and_dfu_across_notify() -> None:
    device = Device("78:66:A5:D3:47:1E", name="MY_SCALE")
    device._merge_discovered(CompatibilityFlag.WEIGHT | CompatibilityFlag.OTA_DFU)
    device._handle_capabilities(LIVE_A0)
    caps = device.capabilities
    assert caps is not None
    assert CompatibilityFlag.WEIGHT in caps.compatibility
    assert CompatibilityFlag.OTA_DFU in caps.compatibility
    assert CompatibilityFlag.NUTRITION in caps.compatibility


@pytest.mark.asyncio
async def test_first_weight_sets_weight_compatibility() -> None:
    device = Device("78:66:A5:D3:47:1E", name="MY_SCALE")
    await device._dispatch_notification(bytes([0xA6, 0x02, 0x7C, 0xB8, 0x00, 0x01]))
    assert device.capabilities is not None
    assert CompatibilityFlag.WEIGHT in device.capabilities.compatibility


@pytest.mark.asyncio
async def test_probe_compatibility_sees_dfu_service() -> None:
    from tests.test_transport import (
        CHAR_NOTIFY_UUID,
        CHAR_WRITE_UUID,
        SERVICE_UUID,
        FakeChar,
        FakeClient,
        FakeService,
        FakeServices,
        _transport,
    )

    client = FakeClient(
        FakeServices(
            [
                FakeService(
                    str(SERVICE_UUID),
                    [
                        FakeChar(str(CHAR_WRITE_UUID), ["write"]),
                        FakeChar(str(CHAR_NOTIFY_UUID), ["notify"]),
                    ],
                ),
                FakeService(str(DFU_SERVICE_UUID), []),
            ]
        )
    )
    transport = _transport(client)
    await transport.connect()
    device = Device(
        "78:66:A5:D3:47:1E",
        name="MY_SCALE",
        transport=transport,
    )
    caps = await device.probe_compatibility()
    assert CompatibilityFlag.OTA_DFU in caps.compatibility
    assert CompatibilityFlag.FILE_TRANSFER not in caps.compatibility
