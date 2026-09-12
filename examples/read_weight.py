#!/usr/bin/env python3
"""Example: connect to a MY_SCALE kitchen scale and print live weight."""

from __future__ import annotations

import argparse
import asyncio
import logging

from icomon_kitchen import KitchenScaleClient, Unit, WeightReading


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if verbose:
        logging.getLogger("bleak").setLevel(logging.DEBUG)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="MY_SCALE", help="BLE advertised name")
    parser.add_argument("--address", help="Optional BLE MAC address")
    parser.add_argument("--seconds", type=float, default=30.0, help="Run duration")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log GATT writes/notifies (DEBUG) including bleak",
    )
    parser.add_argument(
        "--unit",
        choices=[unit.name for unit in Unit],
        help="Optionally switch unit after connect",
    )
    args = parser.parse_args()
    _configure_logging(args.verbose)

    client = KitchenScaleClient()
    device = await client.scan_for_device(name=args.name, address=args.address)
    print(f"Connecting to {device.info.ble_name} at {device.info.address}…")

    async with device:
        print(
            f"Connected. Waiting up to {args.seconds:g}s for weight notifies "
            "(place an item on the scale)…"
        )
        if args.unit is not None:
            await device.set_unit(Unit[args.unit])
            print(f"Unit set to {args.unit}")

        received = 0

        def on_weight(reading: WeightReading) -> None:
            nonlocal received
            received += 1
            print(
                f"{reading.grams:.1f} g "
                f"({reading.milligrams} mg, unit={reading.unit.name}, "
                f"stable={reading.stable})"
            )

        unsubscribe = device.subscribe_weight(on_weight)
        try:
            await asyncio.sleep(args.seconds)
        finally:
            unsubscribe()

        if received == 0:
            print(
                "No weight notifications received. Re-run with -v to inspect "
                "GATT traffic."
            )
            return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
