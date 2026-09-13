#!/usr/bin/env python3
"""Listen for on-device “Hello Vita” food-selection notifies."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples._common import add_device_args, configure_logging, open_device, run
from pyfitdaysplus import VOICE_WAKE_PHRASE, Event, FoodInfoNotify


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_device_args(parser)
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()
    configure_logging(args.verbose)

    device = await open_device(args)
    print(f"connecting {device.info.ble_name} {device.info.address}")
    print(f"say {VOICE_WAKE_PHRASE!r} at the scale")

    def on_food(notify: FoodInfoNotify) -> None:
        print(f"0x{notify.raw_type:02x} {notify.raw_payload.hex()}")
        for food in notify.foods:
            print(f"  id={food.food_id} index={food.food_index}")

    device.subscribe(Event.FOOD, on_food)
    async with device:
        await asyncio.sleep(args.seconds)
    return 0


if __name__ == "__main__":
    run(main)
