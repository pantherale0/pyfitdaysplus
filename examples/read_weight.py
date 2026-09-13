#!/usr/bin/env python3
"""Print live weight (optional tare / unit / send-food)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples._common import add_device_args, configure_logging, open_device, run
from pyfitdaysplus import (
    CommonFood,
    CompatibilityFlag,
    Event,
    NutritionFact,
    NutritionFactType,
    Unit,
    WeightReading,
)


def _demo_facts() -> list[NutritionFact]:
    # Wire types that appeared on a live D6 write (0, 1, 2, 4, 5).
    return [
        NutritionFact(NutritionFactType.CALORIE, 100.0),
        NutritionFact(NutritionFactType.TOTAL_CALORIE, 100.0),
        NutritionFact(NutritionFactType.TOTAL_FAT, 5.0),
        NutritionFact(NutritionFactType.TOTAL_CARBOHYDRATE, 20.0),
        NutritionFact(NutritionFactType.TOTAL_FIBER, 5.0),
    ]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_device_args(parser)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--tare", action="store_true")
    parser.add_argument("--unit", choices=[unit.name for unit in Unit])
    parser.add_argument(
        "--send-food",
        action="store_true",
        help="Upload a food (D6+D5) before weigh/✓; re-upload after each tick",
    )
    parser.add_argument("--food-id", type=int, default=42)
    parser.add_argument("--food-name", default="oats")
    args = parser.parse_args()
    configure_logging(args.verbose)

    device = await open_device(args)
    print(f"connecting {device.info.ble_name} {device.info.address}")

    async with device:
        if args.unit is not None:
            await device.set_unit(Unit[args.unit])
            print(f"unit {args.unit}")
        if args.tare:
            await device.tare()
            print("tare sent")
        if args.send_food:
            facts = _demo_facts()
            food = CommonFood(
                food_id=args.food_id,
                name=args.food_name,
                weight=100,
                facts=tuple(facts),
            )
            caps = device.capabilities
            named = bool(
                caps is not None and caps.supports(CompatibilityFlag.COMMON_FOOD)
            )
            print(
                "named-food D6 "
                + ("advertised" if named else "not advertised; sending anyway")
            )
            await asyncio.sleep(0.5)
            await device.set_common_food(food)
            await device.set_nutrition(args.food_id, facts)
            print(
                f"uploaded food_id={args.food_id} "
                f"(D6 name={args.food_name!r} may not appear on LCD); "
                "weigh, press ✓ once, then upload again before the next ✓ "
                f"(leave this running, default {args.seconds:.0f}s)"
            )

        def on_weight(reading: WeightReading) -> None:
            print(
                f"{reading.value:.2f} {reading.unit.symbol}  "
                f"stable={reading.stable}  "
                f"tare={reading.is_tare}  "
                f"food={reading.food_id}"
            )

        def on_tick(reading: WeightReading) -> None:
            print(
                f"tick {reading.value:.2f} {reading.unit.symbol}  "
                f"food={reading.food_id}  "
                "(re-upload food before the next ✓)"
            )

        stop_weight = device.subscribe(Event.WEIGHT, on_weight)
        stop_tick = device.subscribe(Event.TICK, on_tick)
        try:
            await asyncio.sleep(args.seconds)
        finally:
            stop_weight()
            stop_tick()
    return 0


if __name__ == "__main__":
    run(main)
