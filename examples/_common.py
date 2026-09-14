"""Shared CLI bits for example scripts."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Callable, Coroutine

from bleak import BleakScanner

from pyfitdaysplus import Device

DEFAULT_NAME = "MY_SCALE"


def add_device_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", default=DEFAULT_NAME, help="BLE advertised name")
    parser.add_argument("--address", help="BLE MAC address")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG logs including bleak",
    )


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if verbose:
        logging.getLogger("bleak").setLevel(logging.DEBUG)


async def open_device(args: argparse.Namespace) -> Device:
    if args.address:
        ble_device = await BleakScanner.find_device_by_address(args.address)
        if ble_device is None:
            msg = f"no BLE device found at {args.address}"
            raise SystemExit(msg)
    else:
        ble_device = await BleakScanner.find_device_by_name(args.name)
        if ble_device is None:
            msg = f"no BLE device found with name {args.name!r}"
            raise SystemExit(msg)
    return Device(ble_device)


def run(main: Callable[[], Coroutine[object, object, int]]) -> None:
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
