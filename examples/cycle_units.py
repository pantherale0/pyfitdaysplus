#!/usr/bin/env python3
"""Walk display units via set_unit and print the live unit."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples._common import add_device_args, configure_logging, open_device, run
from pyfitdaysplus import Unit

CYCLE = (
    Unit.G,
    Unit.ML,
    Unit.FL_OZ_WATER,
    Unit.OZ,
    Unit.LB,
    Unit.MG,
    Unit.ML_MILK,
    Unit.FL_OZ_MILK,
    Unit.G,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_device_args(parser)
    parser.add_argument("--wait", type=float, default=2.0)
    args = parser.parse_args()
    configure_logging(args.verbose)

    device = await open_device(args)
    print(f"connecting {device.info.ble_name} {device.info.address}")

    async with device:
        failed: list[str] = []
        for unit in CYCLE:
            await device.set_unit(unit)
            await asyncio.sleep(args.wait)
            latest = device.weight
            got = None if latest is None else latest.unit
            status = "ok" if got is unit else "FAIL"
            live = "none" if got is None else got.name
            print(f"{status:4} set={unit.name:12} live={live}")
            if got is not unit:
                failed.append(unit.name)
        print(f"failed={failed or 'none'}")
        return 1 if failed else 0


if __name__ == "__main__":
    run(main)
