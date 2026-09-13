#!/usr/bin/env python3
"""Print funInfo + GATT compatibility flags."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples._common import add_device_args, configure_logging, open_device, run
from icomon_kitchen import CompatibilityFlag


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_device_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    device = await open_device(args)
    print(f"connecting {device.info.ble_name} {device.info.address}")

    async with device:
        caps = await device.probe_compatibility()
        names = ", ".join(flag.name or str(int(flag)) for flag in caps.flags)
        print(f"vendor      0x{int(caps.function_flags):08x}")
        print(f"compat      0x{int(caps.compatibility):08x}")
        print(f"flags       {names or '(none)'}")
        print(f"nutrition   {caps.supports(CompatibilityFlag.NUTRITION)}")
        print(f"common food {caps.supports(CompatibilityFlag.COMMON_FOOD)}")
        print(f"dfu         {caps.supports(CompatibilityFlag.OTA_DFU)}")
        battery = device.latest_battery
        if battery is not None:
            print(f"battery     {battery.percent}% (type {battery.battery_type})")
        await device.read_weight()
        reading = device.latest_weight
        if reading is not None:
            print(f"weight      {reading.value:.2f} {reading.unit.symbol}")
    return 0


if __name__ == "__main__":
    run(main)
