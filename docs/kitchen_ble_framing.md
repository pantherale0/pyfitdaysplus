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

Live D6 HCI confirms float values use **`round(value × 100)` → u24 BE** (50 →
5000). The library defaults to this via
`DEFAULT_NUTRITION_SCALE = 100`; pass `scale=1.0` to send unscaled integers.

## 213 / D5 — set nutrition

```
WriteInt(foodId BE)          // u32 BE
WriteByte(count)
repeat count times:
  WriteByte(type)            // ICKitchenScaleNutritionFactType ordinal 0..15
  Write3ByteScaled(value)    // u24 BE, default scale ×100
```

## 214 / D6 — common food (verified live HCI)

```
WriteShort(length BE)        // length = len(payload_block) + 2 (includes self)
WriteInt(foodId BE)
WriteByte(0x81)              // splitData / common-food marker (before name)
WriteByte(name_len); WriteBytes(name)
WriteByte(icon_len); WriteBytes(icon)
WriteShort(weight BE)        // u16 BE
WriteByte(magnification)
repeat until end:
  WriteByte(type) + scaled value (2-byte BE if value <= 0xFF else 3-byte BE)
```

Example frame (checksum-valid btsnoop salvage):

`ac4200260005f6df81097465737420666f6f6400006405000013880100145002001518040020d6a4`

- `foodId` = 390879 (`0x0005f6df`)
- name = `test food`, weight = 100, magnification = 5
- facts (u24 / compact): type0=5000, type1=5200, type2=5400, type4=32 (2-byte value)

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
- D7 indexed layout assumed (`foodIndex` before length block); not yet captured on HCI.
