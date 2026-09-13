# pyfitdaysplus

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
pip install pyfitdaysplus
# or from a clone
uv sync
```

Requires Python 3.10+, [`bleak`](https://github.com/hbldh/bleak) for BLE, and a Linux/macOS/Windows host with Bluetooth.

## Quick start

```python
import asyncio
from pyfitdaysplus import KitchenScaleClient, Unit


async def main() -> None:
    client = KitchenScaleClient()
    device = await client.scan_for_device(name="MY_SCALE")
    # or: device = await client.scan_for_device(address="78:66:A5:D3:47:1E")

    async with device:
        reading = await device.async_get_weight()
        print(f"{reading.grams:.1f} g")
        await device.tare()
        await device.set_unit(Unit.G)


asyncio.run(main())
```

### Sync cache and event callbacks

Notifications update an in-memory cache as they arrive. Sync code can read
`device.weight` (or `device.battery`, `device.food`, `device.ack`) without
`await`, and you can subscribe to live updates:

```python
from pyfitdaysplus import Event


def on_weight(reading):
    print(f"{reading.grams:.1f} g, stable={reading.stable}")


unsubscribe = device.subscribe(Event.WEIGHT, on_weight)


def on_tick(reading):
    print(f"tick {reading.grams:.1f} g")


unsubscribe_tick = device.subscribe(Event.TICK, on_tick)

# From sync code (e.g. a UI timer or callback):
reading = device.weight
grams = None if reading is None else reading.grams

unsubscribe()  # stop receiving callbacks
unsubscribe_tick()
```

Example scripts (shared `--name` / `--address` / `-v`):

| Script | What it does |
| --- | --- |
| `examples/read_weight.py` | Stream live weight (`--tare`, `--unit G`, `--send-food`, `--seconds`) |
| `examples/show_capabilities.py` | Print `CompatibilityFlag` after `probe_compatibility()` |
| `examples/cycle_units.py` | Walk `set_unit` through kitchen units |
| `examples/listen_voice.py` | Print `0xAF` food-selection notifies (“Hello Vita”) |

```bash
uv run python examples/read_weight.py --name MY_SCALE
uv run python examples/read_weight.py --tare --unit G
uv run python examples/read_weight.py --send-food --seconds 60
uv run python examples/show_capabilities.py --address 78:66:A5:D3:47:1E
uv run python examples/cycle_units.py --name MY_SCALE
uv run python examples/listen_voice.py --name MY_SCALE
```

## Public API

- `KitchenScaleClient.scan_for_device(name=..., address=...)`
- `Device.connect()` / `disconnect()` / async context manager
- `device.weight` / `device.battery` / `device.food` / `device.ack` — sync caches
- `await device.async_get_weight()` — cached reading, or wait for the first notify
- `device.subscribe(Event.WEIGHT, callback)` — event callbacks (returns unsubscribe)
- `device.subscribe(Event.TICK, callback)` — hardware ✓ after a food upload (`0xAC` on KG2458; **one confirm per upload**)
- `device.subscribe(Event.FOOD, callback)` / `subscribe(Event.CAPABILITIES, …)` / `subscribe(Event.BATTERY, …)`
- `async for reading in device.weights(): ...`
- `await device.tare()`
- `await device.confirm()` — D2 type 10 (app “confirm food”; the hardware ✓ is `Event.TICK`)
- `await device.set_unit(Unit.G)` (also `ML`, `LB`, `OZ`, …)
- `await device.read_food_selection()` → `FoodInfoNotify` with `count` / `foods`
- `async for notify in device.food_selections():` — `notify.foods` is `foodId` + `food_index`
- `await device.set_nutrition(food_id, facts)` — cmd **213 / D5**
- `await device.set_common_food(food)` — cmd **214 / D6** (split when long)
- `await device.set_common_food_indexed(food_index, food)` — cmd **215 / D7**
- `await device.delete_common_foods(entries)` — cmd **220 / DC** on protocol 113
- Low-level encode helpers: `build_set_nutrition_frame`, `encode_nutrition_value_u24`, …
- `device.capabilities` / `parse_fun_info` — vendor `DeviceFunction` bits plus
  `CompatibilityFlag` (`caps.flags`, `caps.supports(CompatibilityFlag.NUTRITION)`)
- `device.battery` / `caps.battery` — percent from ``funInfo`` (`0xA0`)
- `await device.probe_compatibility()` — merge funInfo with GATT (FFB4, Nordic DFU)
  and live weight, without extra command writes
- Injectable BLE backend via `KitchenScaleClient(backend=...)` for tests

No raw UUIDs or wire command bytes are required for normal kitchen-scale use.

### On-device voice food selection

The **KG2458ULB-D** microphone runs offline AI food recognition locally (wake
**“Hello Vita”**). Fitdays+ handles notify **`0xAF` / 175** only after native
**`libICBleProtocol.so`** decodes BLE bytes into a Java map:

- `count` (int)
- `foods`: list of `{ foodId, foodIndex }`
- empty when `count == 0`

Java never sees raw offsets. This library unwraps splitData the same way and
fills **`count` / `foods`**. Native packing is ``count u8`` then
``foodIndex u8 | foodId u32 BE`` per hit (identical to delete D8/DC).

```python
from pyfitdaysplus import Event, KitchenScaleClient, parse_food_info_notify

client = KitchenScaleClient()
device = await client.scan_for_device(name="MY_SCALE")


def on_voice_food(notify):
    print(notify.raw_payload.hex())
    for food in notify.foods:
        print(food.food_id, food.food_index)


device.subscribe(Event.FOOD, on_voice_food)

async with device:
    notify = await device.read_food_selection()
    parsed = parse_food_info_notify(notify.raw_payload)
```

We do **not** stream audio or inject the **“Hello Vita”** wake phrase over BLE.

### Writing custom food + nutrition (recommended)

**Upload a food with your nutrition facts, then enter food-weigh mode.** Do
that **before** each ✓. The scale’s LCD may still show a firmware catalog
name (live KG2458 used USDA-style ids, e.g. 1077 → “MILK WHOLE”). Trust the
macros you just sent, not the onboard US table. After ✓ the scale saves
once (`Event.TICK` / history ``0xAC``) and will not tick again until
you upload another food.

```python
from pyfitdaysplus import CommonFood, Event, NutritionFact, NutritionFactType

food = CommonFood(
    food_id=42,
    name="Oats",
    weight=100,
    facts=(NutritionFact(NutritionFactType.PROTEIN, 12.0),),
)


def on_tick(reading):
    print(reading.grams, reading.food_id)


async with device:
    device.subscribe(Event.TICK, on_tick)
    await device.set_common_food(food)
    await device.set_nutrition(food.food_id, list(food.facts))
    # weigh, press ✓ → on_tick once
    # upload again before the next ✓
```

| Method | Cmd | Notes |
| --- | --- | --- |
| `set_nutrition(food_id, facts)` | 213 / D5 | facts only (no LCD name); native ×10 |
| `set_common_food(food)` | 214 / D6 | splitData chunks: `total_len \| seq \| slice` |
| `set_common_food_indexed(food_index, food)` | 215 / D7 | `food_index` prefixes logical payload |
| `delete_common_foods(entries)` | 220 / DC | Protocol 113 default; pass `use_alt_delete=False` for 216 / D8 |

D5 native ×10 (150 kcal → wire 1500); D6/D7 default ×100; pass `scale=1.0` for raw integers.

**Still stubbed**

- **FFB4** icon file upload (D9 metadata is known; chunks cmd 65440 not sent).
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

Live weight arrives on notify type **`0xA6`** (`ICKitchenScaleData`). 14-byte
splitData body:

| Offset | Field |
| --- | --- |
| 0 | flags: `0x80` unstable/negative, `0x40` tare; idle frames also set `0x01` |
| 1 | unit ordinal in the high nibble (`unit << 4`) |
| 2–4 | milligrams u24 BE (Fitdays field `b`) |
| 5–8 | `foodId` u32 BE (firmware catalog; 0 when idle) |
| 9–12 | `userId` u32 BE |
| 13 | `isOk` (front-panel ✓ does **not** set this on KG2458; use history `0xAC`) |

Voice food selection uses notify **`0xAF`** (`ICFoodInfo`):
`count u8 | (foodIndex u8 + foodId u32 BE)…`. Java maps still use
`foods[{ foodId, foodIndex }]`.

User info for firmware ≥ 66 is cmd **219 / DB**: `time u32`, `utc_offset u16`,
`userId u32`, `rnis` count, then each `{ type u8, cur_rni u24 ×10, max_rni u24 ×10, progress u16 }`. Older firmware uses cmd **208** without the `rnis` list.

File-info cmd **217 / D9** (before FFB4): `fileType u8`, `foodIndex u8`,
`fileSize u32`, `foodId u32`, `cs u8`.

## Known unknowns

- Remaining ``funInfo`` (`0xA0`) precision bytes after the flag u32 (`divG` /
  `divOZ` / `maxG` / liquid units). Flags + battery percent (offset 15) are parsed
- No kitchen BLE **voice-language** command; `ICDeviceFunctionVoiceLanguage` is
  bit 4 and is **clear** on live KG2458 (`0x00fc4f02`). Other SKUs use body-scale
  sound-mode UI
- **“Hello Vita”** ASR is on-device only; no GATT PCM/audio stream in the SDK
- **FFB4** file chunks after D9 are not implemented (inline D6/D7 `icon` only)
- Legacy protocols **110/111** (stubs only via shared models)
- BLE **advertisement manufacturer data** (scan matches `local_name` only)

## Development

```bash
uv run pytest
uv run mypy pyfitdaysplus
uv run ruff check .
```

## License

MIT
