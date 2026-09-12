# ICOMON Kitchen Scale

Async, fully typed Python library for the **ICOMON / Fitdays+** smart kitchen scale **KG2458ULB-D** (BLE name **`MY_SCALE`**, protocol **113 GeneralV2**).

Generated from [`pantherale0/python-library-template`](https://github.com/pantherale0/python-library-template) via Copier.

## Supported hardware

| Field | Value |
| --- | --- |
| Model | `KG2458ULB-D` |
| BLE name | `MY_SCALE` |
| Example MAC | `78:66:A5:D3:47:1E` |
| Firmware (observed) | 1.5.3 |
| Hardware (observed) | 1.0.0 |
| Wire `device_type` | `0x42` (protocol 113) |

GATT service `FFB0` with write `FFB1`, notify `FFB2`, file write `FFB4`, and DIS `180A`. Characteristics are discovered by UUID — handles are not hardcoded.

## Install

```bash
uv sync
# or
pip install -e .
```

Requires Python 3.10+, [`bleak`](https://github.com/hbldh/bleak) for BLE, and a Linux/macOS/Windows host with Bluetooth.

## Quick start

```python
import asyncio
from icomon_kitchen import KitchenScaleClient, Unit

async def main() -> None:
    client = KitchenScaleClient()
    device = await client.scan_for_device(name="MY_SCALE")
    # or: device = await client.scan_for_device(address="78:66:A5:D3:47:1E")

    async with device:
        reading = await device.weight
        print(f"{reading.grams:.1f} g")
        await device.tare()
        await device.set_unit(Unit.G)

asyncio.run(main())
```

Example script:

```bash
uv run python examples/read_weight.py --name MY_SCALE
```

## Public API

- `KitchenScaleClient.scan_for_device(name=..., address=...)`
- `KitchenScaleDevice.connect()` / `disconnect()` / async context manager
- `await device.weight` — latest live reading
- `async for reading in device.weights(): ...`
- `await device.tare()`
- `await device.set_unit(Unit.G)` (also `ML`, `LB`, `OZ`, …)
- Injectable BLE backend via `KitchenScaleClient(backend=...)` for tests

No raw UUIDs or wire command bytes are required for normal kitchen-scale use.

## Protocol notes

General/V2 frames use magic `0xAC`, `device_type`, payload, trailing command byte, and an **8-bit additive checksum** (not CRC16) over bytes from index 2 through `len-2`.

Verified TX vectors for `device_type=0x42`:

| Command | Hex |
| --- | --- |
| `app_reply` (209 / D1) | `ac42000200a000d173` |
| `read_history` (212 / D4) | `ac42000000d4d4` |
| `tare` (210 / D2, type 0) | built via setting path |

Live weight arrives on notify type **`0xA6`** (`ICKitchenScaleData`). The Fitdays app exposes weight field `b` in **milligrams** (163000 → 163.0 g).

## Fitdays cloud

HTTP/cloud sync is **not implemented**. `icomon_kitchen.cloud.FitdaysCloudClient` is a stub for future work.

## Known unknowns

- Full **`0xA6`** notify field map (stable/unit offsets are best-effort)
- Nutrition commands use a **24-bit scale** not fully mapped here
- Legacy protocols **110/111** are not wired yet (stubs only via shared models)
- BLE **advertisement manufacturer data** layout for model detection
- Optional **`0xDB` user_info_rnis** payload details for firmware ≥ specific versions

## Development

```bash
uv run pytest
uv run mypy icomon_kitchen
uv run ruff check .
```

## License

MIT
