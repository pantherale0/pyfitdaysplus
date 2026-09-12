# Kitchen BLE framing (Phase 1 native notes + round-2 live HCI)

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

Round-2 D6 HCI confirms float values use **`round(value × 100)` → wire integer**
(50 → 5000). Default: `DEFAULT_NUTRITION_SCALE = 100`; pass `scale=1.0` for raw
integers.

## 213 / D5 — set nutrition

```
WriteInt(foodId BE)          // u32 BE
WriteByte(count)
repeat count times:
  WriteByte(type)            // ICKitchenScaleNutritionFactType ordinal 0..15
  Write3ByteScaled(value)    // u24 BE, default scale ×100
```

## 214 / D6 — common food (round-2 locked HCI)

After `AC 42`:

1. `u16 BE` length prefix — value **`len(payload) + 2`** (`0x0026` for a 36-byte payload)
2. `foodId` u32 BE
3. **ctrl byte `0x81`** — live-observed; required on wire (purpose unknown)
4. `name_len` u8 + name UTF-8
5. `icon_len` u8 + icon bytes
6. `weight` u16 BE grams
7. `magnification` u8 (capture used `0x05`; Java often sends 0/1)
8. facts: repeated **`type u8` + `value u24 BE`** (no count byte). Values `> 0xFF`
   use 3 bytes; values `<= 0xFF` omit one leading zero byte on wire (2 bytes).
9. trailing cmd **`0xD6`** + 8-bit additive checksum

**Primary frame (locked vector):**

`ac4200260005f6df81097465737420666f6f6400006405000013880100145002001518040020d6a4`

| Field | Value |
| --- | --- |
| foodId | 390879 (`0x0005F6DF`) |
| name | `test food` |
| weight | 100 g |
| magnification | 5 |
| facts (wire / float) | type0=5000/50.0, type1=5200/52.0, type2=5400/54.0, type4=32/0.32 |

**Split continuation (short chunk, same cmd):**

`ac42002601d0050015e0d6c7` — repeats total length `0x0026`, chunk index `0x01`, then
tail bytes. On the **primary** (unsplit) frame, `length = len(payload) + 2`.

Long payloads use **splitData** (multiple D6 frames). Icon bytes may also use FFB4
file transfer — **not implemented** (icon sent inline only).

## 215 / D7 — indexed common food

Same as 214, prefixed with:

```
WriteByte(foodIndex)
```

(the `foodIndex` byte precedes the length-prefixed block)

## 216 / D8 or 220 / DC — delete common foods

Layout **provisional** in this library:

```
WriteByte(count)
repeat count:
  WriteInt(foodId BE)
  WriteByte(foodIndex)
```

Protocol 113 uses **220 / DC** by default.

## Nutrition fact types (`ICKitchenScaleNutritionFactType`)

Ordinals **0..15**: Calorie, TotalCalorie, TotalFat, SaturatedFat, TransFat,
Cholesterol, Sodium, TotalCarbohydrate, DietaryFiber, Sugar, Protein, VitaminA,
VitaminC, Calcium, Iron, Reserved.

## Provisional / TODO

- **FFB4** icon file upload path.
- Delete payload confirmation on live HCI.
- Meaning of ctrl byte **`0x81`** (required; do not omit when encoding).
- D7 indexed layout assumed (`foodIndex` before length block); not yet captured on HCI.
