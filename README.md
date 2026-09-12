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

This release focuses on **weight, tare, unit**, **General/V2 framing**,
**decoding voice food selections** from notify **`0xAF`**, and **Phase 2v2
stubs** for sending custom food + nutrition **to** the device. Voice recognition
runs **on the scale microphone** (offline ASR, wake **“Hello Vita”**, English,
~500 foods); the client only receives food IDs over BLE — **no phone mic** and
**no PCM/audio streaming** over GATT.

Optional hooks also parse **`0xA0` (`funInfo`)** capability bits. Wake-word
triggering and audio transport are **not implemented**.

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
- `await device.read_food_selection()` → `FoodInfoNotify` with `raw_payload`
- `async for notify in device.food_selections():` — decode `notify.foods` when wire map exists
- `device.set_food_selection_handler(callback)` for voice ASR **`0xAF`** notifies
- `await device.set_nutrition(food_id, facts)` — cmd **213 / D5**
- `await device.set_common_food(food)` — cmd **214 / D6** (split when long)
- `await device.set_common_food_indexed(food_index, food)` — cmd **215 / D7**
- `await device.delete_common_foods(entries)` — cmd **220 / DC** on protocol 113
- Low-level encode helpers: `build_set_nutrition_frame`, `encode_nutrition_value_u24`, …
- `device.capabilities` / `parse_fun_info` for optional voice capability bits
- Injectable BLE backend via `KitchenScaleClient(backend=...)` for tests

No raw UUIDs or wire command bytes are required for normal kitchen-scale use.

### On-device voice food selection

The **KG2458ULB-D** microphone runs offline AI food recognition locally (wake
**“Hello Vita”**). Fitdays+ handles notify **`0xAF` / 175** only after native
**`libICBleProtocol.so`** decodes BLE bytes into a Java map:

- `count` (int)
- `foods`: list of `{ foodId, foodIndex }`
- empty when `count == 0`

Java never sees raw offsets. This library recognizes **`0xAF`**, preserves
**`raw_payload`**, and leaves **`count` / `foods` empty** until the wire layout
is verified (see `icomon_kitchen/protocol/food_info.py`).

```python
from icomon_kitchen import KitchenScaleClient, parse_food_info_notify

client = KitchenScaleClient()
device = await client.scan_for_device(name="MY_SCALE")

def on_voice_food(notify):
    print(notify.raw_payload.hex())
    for food in notify.foods:
        print(food.food_id, food.food_index)

device.set_food_selection_handler(on_voice_food)

async with device:
    notify = await device.read_food_selection()
    parsed = parse_food_info_notify(notify.raw_payload)
```

We do **not** stream audio or inject the **“Hello Vita”** wake phrase over BLE.

### Writing custom food + nutrition (Phase 2v2)

Send nutrition facts and custom food entries **to** the scale. Wire layouts follow
Phase 1 native notes in [`docs/kitchen_ble_framing.md`](docs/kitchen_ble_framing.md).

| Method | Cmd | Notes |
| --- | --- | --- |
| `set_nutrition(food_id, facts)` | 213 / D5 | `facts`: `NutritionFact(type, value)` |
| `set_common_food(food)` | 214 / D6 | splitData chunks: `total_len \| seq \| slice` |
| `set_common_food_indexed(food_index, food)` | 215 / D7 | `food_index` prefixes logical payload |
| `delete_common_foods(entries)` | 220 / DC | Protocol 113 default; pass `use_alt_delete=False` for 216 / D8 |

```python
from icomon_kitchen import (
    CommonFood,
    FoodReference,
    KitchenScaleClient,
    NutritionFact,
    NutritionFactType,
)

food = CommonFood(
    food_id=42,
    name="Oats",
    icon=b"\x01\x02",  # inline bytes only; FFB4 file upload not implemented
    weight=500,
    facts=(NutritionFact(NutritionFactType.PROTEIN, 12.0),),
)

async with device:
    await device.set_nutrition(
        42,
        [NutritionFact(NutritionFactType.CALORIE, 150.0)],
    )  # default scale ×100 → wire 15000; pass scale=1.0 for raw integers
    await device.set_common_food(food)
    await device.set_common_food_indexed(3, food)
    await device.delete_common_foods([FoodReference(food_id=42, food_index=3)])
```

**Provisional / TODO**

- **Delete payload** layout (`count | foodId | foodIndex`) is provisional.
- **FFB4** icon file upload remains stubbed (inline `icon` bytes only).
- D6 reassembled layout: `foodId u32 | name | icon | weight u16 | fact_count | facts`
- splitData per chunk: `total_len u16 | seq u8 | slice` (see `docs/kitchen_ble_framing.md`)

## Protocol notes

General/V2 frames use magic `0xAC`, `device_type`, payload, trailing command byte, and an **8-bit additive checksum** (not CRC16) over bytes from index 2 through `len-2`.

Verified TX vectors for `device_type=0x42`:

| Command | Hex |
| --- | --- |
| `app_reply` (209 / D1) | `ac42000200a000d173` |
| `read_history` (212 / D4) | `ac42000000d4d4` |
| `tare` (210 / D2, type 0) | built via setting path |

Live weight arrives on notify type **`0xA6`** (`ICKitchenScaleData`). The Fitdays app exposes weight field `b` in **milligrams** (163000 → 163.0 g).

Voice food selection uses notify **`0xAF`** (`ICFoodInfo`). Decoded Java shape:
`count` + `foods[{ foodId, foodIndex }]`. **BLE byte packing is unknown** in v1;
use `FoodInfoNotify.raw_payload`.

## Fitdays cloud

HTTP/cloud sync is **not implemented**. `icomon_kitchen.cloud.FitdaysCloudClient` is a stub for future work.

## Known unknowns

- Full **`0xA6`** notify field map (stable/unit offsets are best-effort)
- **`0xAF` BLE payload packing** for `count` / `foods[{ foodId, foodIndex }]` (native decode only today)
- Exact **`funInfo`** bit map for `ICDeviceFunctionVoiceAssistant` / `ICDeviceFunctionVoiceLanguage`
- Whether voice language selection has a documented BLE setting command
- No wire evidence for **“Hello Vita”** wake triggering or **audio/PCM** streaming over GATT
- Nutrition u24 values default to **×100** scale (live D6 verified); override with `scale=`
- Delete-common-food wire layout is **provisional**; protocol 113 prefers cmd **220 / DC**
- **FFB4** icon file transfer is not implemented (inline icon bytes in D6/D7 only)
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
