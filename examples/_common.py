"""Shared CLI bits for example scripts."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Callable, Coroutine

from pyfitdaysplus import Device, KitchenScaleClient

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
    client = KitchenScaleClient()
    return await client.scan_for_device(name=args.name, address=args.address)


def run(main: Callable[[], Coroutine[object, object, int]]) -> None:
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
