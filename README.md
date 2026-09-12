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
| On-device voice | Wake phrase **“Hello Vita”** (English); ~500 foods; ASR on scale |

GATT service `FFB0` with write `FFB1`, notify `FFB2`, file write `FFB4`, and DIS `180A`. Characteristics are discovered by UUID — handles are not hardcoded.

## v1 scope

This release focuses on **weight, tare, unit**, and **General/V2 framing**. Voice recognition runs **on the scale microphone** (offline ASR); Fitdays+ receives structured food/nutrition over BLE — there is **no phone mic** and **no PCM/audio streaming** over GATT in v1.

Optional hooks parse notify types **`0xA0` (`funInfo`)** for capability bits and **`0xAF` (`ICFoodInfo`)** after on-device voice recognition. Wake-word handling and audio transport are **not implemented** without clear wire evidence.

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
- Optional voice/food hooks (stubs): `await device.read_food_info()`, `device.capabilities`, `parse_fun_info` / `parse_food_info`
- Injectable BLE backend via `KitchenScaleClient(backend=...)` for tests

No raw UUIDs or wire command bytes are required for normal kitchen-scale use.

### On-device voice (Phase 2 hooks)

The **KG2458ULB-D** includes a microphone for offline AI food recognition (wake: **`Hello Vita`**, English catalog ~500 foods). Recognition executes on the scale; the app receives **`ICFoodInfo`** payloads on notify **`0xAF`**. Capability bits such as **`ICDeviceFunctionVoiceAssistant`** and **`ICDeviceFunctionVoiceLanguage`** may appear in **`funInfo`** (`0xA0`).

```python
from icomon_kitchen import DeviceFunction, KitchenScaleClient

client = KitchenScaleClient()
device = await client.scan_for_device(name="MY_SCALE")

def on_capabilities(caps):
    if caps.voice_assistant:
        print("Scale reports on-device voice ASR")

device.set_capabilities_handler(on_capabilities)

async with device:
    food = await device.read_food_info()  # after user speaks on the scale
    print(food.food_id, food.nutrition_payload)
```

We do **not** stream audio or trigger **“Hello Vita”** over BLE in this version.

## Protocol notes

General/V2 frames use magic `0xAC`, `device_type`, payload, trailing command byte, and an **8-bit additive checksum** (not CRC16) over bytes from index 2 through `len-2`.

Verified TX vectors for `device_type=0x42`:

| Command | Hex |
| --- | --- |
| `app_reply` (209 / D1) | `ac42000200a000d173` |
| `read_history` (212 / D4) | `ac42000000d4d4` |
| `tare` (210 / D2, type 0) | built via setting path |

Live weight arrives on notify type **`0xA6`** (`ICKitchenScaleData`). The Fitdays app exposes weight field `b` in **milligrams** (163000 → 163.0 g).

Voice-derived food uses notify **`0xAF`** (`ICFoodInfo`). Device functions (including voice assistant/language) may be advertised in **`0xA0`** (`funInfo`); bit positions in this library are provisional.

## Fitdays cloud

HTTP/cloud sync is **not implemented**. `icomon_kitchen.cloud.FitdaysCloudClient` is a stub for future work.

## Known unknowns

- Full **`0xA6`** notify field map (stable/unit offsets are best-effort)
- Full **`0xAF` / `ICFoodInfo`** layout (v1 exposes provisional `food_id` + raw tail)
- Exact **`funInfo`** bit map for `ICDeviceFunctionVoiceAssistant` / `ICDeviceFunctionVoiceLanguage`
- Whether voice language selection has a documented BLE setting command
- No wire evidence for **“Hello Vita”** wake triggering or **audio/PCM** streaming over GATT
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
