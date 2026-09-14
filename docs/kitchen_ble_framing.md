# Kitchen BLE framing (Phase 1 native notes + live HCI)

General/V2 command frames: `AC | device_type | payload… | cmd | checksum`.

This document covers **writing custom food + nutrition to the scale** (app → device).

**Recommended session (Fitdays+ 1.14.1 on KG2458, live HCI 2026-09-13):**

1. D6 named food (even at 0 g).
2. When a stable non-zero weight appears, **D6 again** (same payload).
3. Front-panel ✓ → history ``0xAC``. App replies with D1 ``00 ac 00``.
4. After confirm, D6 the same food again (re-arm while weight still on the plate).
5. When the plate returns to 0 g, D6 **clear**: `foodId=0`, empty name, 100 g, zero facts.
6. Next food: D6 at 0 g, then D6 again when weight returns, then ✓.

**Library session:** `start_food_weigh` / `stop_food_weigh` own this sequence.
Integrators should not send D5 or re-upload after ✓.

**History dump:** after connect the app sends D4 ``ac42000000d4d4``. The scale
streams stored ✓ as the same ``0xAC`` notify (unix time + mg + foodId + userId).
Ack each with D1 ``00 ac 00``. Java paginates when a callback list has ≥10
records (``HISTORY_PAGE_SIZE``). A dump ``0xAC`` is not a live front-panel ✓.

## Command summary (protocol 113 / KG2458ULB-D)

| Java cmd | Wire | API |
| --- | --- | --- |
| 212 | D4 | `read_history` (scale dumps stored ✓ as `0xAC`; ack each with D1 `00 ac 00`) |
| 213 | D5 | `set_nutrition` |
| 214 | D6 | `start_food_weigh` / `set_common_food` (splitData) |
| 215 | D7 | `set_common_food_indexed` (splitData) |
| 216 | D8 | `delete_common_foods` (legacy) |
| 220 | DC | `delete_common_foods` (protocol 113 preferred) |

## Nutrition value scale

Reassembled D6 HCI confirms float values use **`round(value × 100)` → u24 BE**
(50 → 5000). Default: `DEFAULT_NUTRITION_SCALE = 100`; pass `scale=1.0` for raw
integers.

## splitData framing (D6 / D7)

Each on-wire chunk:

```
AC | device_type 0x42 | total_len u16 BE | seq u8 | payload_slice | cmd | checksum
```

- `total_len` = full **reassembled logical payload** byte length (`0x0026` = 38 in
  the locked capture)
- `seq` = chunk index from 0
- `payload_slice` bytes concatenate in sequence order to form the logical payload

**Locked live pair (cmd `0xD6`):**

```
ac4200260005f6df81097465737420666f6f6400006405000013880100145002001518040020d6a4
ac42002601d0050015e0d6c7
```

## Reassembled logical payload (D6)

After concatenating payload slices (38 bytes in the locked capture):

1. `foodId` u32 BE — **`0x05F6DF81`** (100065153). The former `0x81` “ctrl byte”
   was the low byte of this id spanning a chunk boundary.
2. `name_len` u8 + name UTF-8
3. `icon_len` u8 + icon bytes
4. `weight` u16 BE grams
5. **`fact_count` u8** (5 in capture — not magnification)
6. `count × (type u8 + value u24 BE)`

Locked facts (wire type ordinals vs `supportDataTypes` may differ from enum names):

| type | u24 | float (÷100) |
| --- | --- | --- |
| 0 | 5000 | 50 kcal |
| 1 | 5200 | 52 fat |
| 2 | 5400 | 54 carbs |
| 4 | 8400 | 84 sodium |
| 5 | 5600 | 56 protein |

## 213 / D5 — set nutrition

D5 does **not** include a food name. Fitdays uses it when funInfo has
VoiceAssistant (nutrition) but **not** Restart (named/common food).

On KG2458, a D6 write with UTF-8 `name="oats"` / `foodId=42` still put the
scale into food-weigh mode. The LCD showed **MILK WHOLE** and A6 `foodId`
was **1077** (`0x435`). That matches USDA SR NDB **01077** (US whole milk).
On-scale names and default macros are a **firmware catalog**, not BLE UTF-8
and not UK CoFID / McCance & Widdowson. US and UK foods of the same English
name are not composition-equivalent; treat `food_id` as opaque. Custom D6
names are ignored on this SKU. ✓ then saved history `0xAC` with the same id.

Native `encodeupdateFoodInfo` scales `foodValue` **×10** (`SET_NUTRITION_SCALE`).

```
WriteInt(foodId BE)
WriteByte(count)
repeat count times:
  WriteByte(type)
  Write3ByteScaled(value)    // u24 BE, D5 scale ×10
```

## 215 / D7 — indexed common food

Same reassembled body as D6, prefixed with `food_index u8` before splitData
chunking.

## 216 / D8 or 220 / DC — delete common foods

Native `encodeDeleteFood` (kitchen 42) for **both** opcodes:

```
WriteByte(count)
repeat count:
  WriteByte(foodIndex)
  WriteInt(foodId BE)
```

Java still builds `foods[{ foodId, foodIndex }]`. Notify **`0xAF`** uses the
same byte order. Protocol 113 sends **220 / DC** by default.

## 217 / D9 — file info (FFB4 prelude)

```
WriteByte(fileType)
WriteByte(foodIndex)
WriteInt(fileSize)
WriteInt(foodId)
WriteByte(cs)
```

Chunks on FFB4 use cmd **65440** and are not implemented here.

## 219 / DB — user info (firmware ≥ 66)

```
WriteInt(time)
WriteShort(utc_offset)
WriteInt(userId)
WriteByte(rnis_count)
repeat:
  WriteByte(type)
  Write3Byte(cur_rni × 10)
  Write3Byte(max_rni × 10)
  WriteShort(progress)
```

## Remaining

- FFB4 icon file upload path after D9.
- D7 indexed split capture not yet verified independently.
