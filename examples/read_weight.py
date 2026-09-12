#!/usr/bin/env python3
"""Example: connect to a MY_SCALE kitchen scale and print live weight."""

from __future__ import annotations

import argparse
import asyncio

from icomon_kitchen import KitchenScaleClient, Unit


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="MY_SCALE", help="BLE advertised name")
    parser.add_argument("--address", help="Optional BLE MAC address")
    parser.add_argument("--seconds", type=float, default=30.0, help="Run duration")
    parser.add_argument(
        "--unit",
        choices=[unit.name for unit in Unit],
        help="Optionally switch unit after connect",
    )
    args = parser.parse_args()

    client = KitchenScaleClient()
    device = await client.scan_for_device(name=args.name, address=args.address)
    print(f"Connecting to {device.info.ble_name} at {device.info.address}…")

    async with device:
        if args.unit is not None:
            await device.set_unit(Unit[args.unit])
            print(f"Unit set to {args.unit}")

        deadline = asyncio.get_running_loop().time() + args.seconds
        while asyncio.get_running_loop().time() < deadline:
            reading = await device.weight
            print(
                f"{reading.grams:.1f} g "
                f"({reading.milligrams} mg, unit={reading.unit.name}, "
                f"stable={reading.stable})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
