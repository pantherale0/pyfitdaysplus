#!/usr/bin/env python3
"""Example: listen for on-device “Hello Vita” food selections from MY_SCALE."""

from __future__ import annotations

import argparse
import asyncio
import logging

from icomon_kitchen import (
    VOICE_WAKE_PHRASE,
    DeviceCapabilities,
    FoodInfoNotify,
    KitchenScaleClient,
)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if verbose:
        logging.getLogger("bleak").setLevel(logging.DEBUG)


def on_capabilities(caps: DeviceCapabilities) -> None:
    print(
        f"capabilities flags=0x{caps.function_flags:08x} "
        f"voice_assistant={caps.voice_assistant} "
        f"voice_language={caps.voice_language}"
    )


def on_voice_food(notify: FoodInfoNotify) -> None:
    print(f"food notify 0x{notify.raw_type:02X}: {notify.raw_payload.hex()}")
    if notify.count is not None:
        print(f"  count={notify.count}")
    for food in notify.foods:
        print(f"  food_id={food.food_id} food_index={food.food_index}")
    if notify.count is None and not notify.foods:
        print("  (decoded foods unavailable until 0xAF wire map is verified)")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="MY_SCALE", help="BLE advertised name")
    parser.add_argument("--address", help="Optional BLE MAC address")
    parser.add_argument("--seconds", type=float, default=60.0, help="Run duration")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log GATT writes/notifies (DEBUG) including bleak",
    )
    args = parser.parse_args()
    _configure_logging(args.verbose)

    client = KitchenScaleClient()
    device = await client.scan_for_device(name=args.name, address=args.address)
    print(f"Connecting to {device.info.ble_name} at {device.info.address}…")

    device.set_capabilities_handler(on_capabilities)
    device.set_food_selection_handler(on_voice_food)

    async with device:
        print(
            f"Connected. Say {VOICE_WAKE_PHRASE!r} on the scale "
            "(English, on-device ASR — no phone mic)."
        )
        print(f"Waiting {args.seconds:g}s for food-selection notifies (0xAF)…")
        await asyncio.sleep(args.seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
