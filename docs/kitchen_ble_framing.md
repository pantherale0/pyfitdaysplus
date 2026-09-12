# Kitchen BLE framing (Phase 1 native notes + live HCI)

General/V2 command frames: `AC | device_type | payload… | cmd | checksum`.

This document covers **writing custom food + nutrition to the scale** (app → device).

## Command summary (protocol 113 / KG2458ULB-D)

| Java cmd | Wire | API |
| --- | --- | --- |
| 213 | D5 | `set_nutrition` |
| 214 | D6 | `set_common_food` (splitData) |
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

```
WriteInt(foodId BE)
WriteByte(count)
repeat count times:
  WriteByte(type)
  Write3ByteScaled(value)    // u24 BE, default scale ×100
```

## 215 / D7 — indexed common food

Same reassembled body as D6, prefixed with `food_index u8` before splitData
chunking.

## 216 / D8 or 220 / DC — delete common foods

Layout **provisional**:

```
WriteByte(count)
repeat count:
  WriteInt(foodId BE)
  WriteByte(foodIndex)
```

Protocol 113 uses **220 / DC** by default.

## Provisional / TODO

- **FFB4** icon file upload path.
- Delete payload confirmation on live HCI.
- D7 indexed split capture not yet verified independently.
