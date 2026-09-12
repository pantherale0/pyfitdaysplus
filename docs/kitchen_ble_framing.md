# Kitchen BLE framing (Phase 1 native notes)

General/V2 command frames: `AC | device_type | payload… | cmd | checksum`.

This document covers **writing custom food + nutrition to the scale** (app → device).
Payload layouts come from native `libICBleProtocol.so` notes; **nutrition value
scaling is unverified** in this library.

## Command summary (protocol 113 / KG2458ULB-D)

| Java cmd | Wire | API |
| --- | --- | --- |
| 213 | D5 | `set_nutrition` |
| 214 | D6 | `set_common_food` (splitData) |
| 215 | D7 | `set_common_food_indexed` (splitData) |
| 216 | D8 | `delete_common_foods` (legacy) |
| 220 | DC | `delete_common_foods` (protocol 113 preferred) |

## 213 / D5 — set nutrition

```
WriteInt(foodId BE)          // u32 BE
WriteByte(count)
repeat count times:
  WriteByte(type)            // ICKitchenScaleNutritionFactType ordinal 0..15
  Write3ByteScaled(value)    // u24 BE — scale TODO
```

## 214 / D6 — common food

```
WriteInt(foodId BE)
WriteByte(name_len); WriteBytes(name)
WriteByte(icon_len); WriteBytes(icon)
WriteShort(weight BE)        // u16 BE
WriteByte(magnification)
WriteByte(fact_count)
repeat fact_count:
  WriteByte(type) + 3-byte scaled value
```

Long payloads use **splitData** (multiple D6 frames). Icon bytes may also use FFB4
file transfer — **not implemented** in v1 (icon sent inline only).

## 215 / D7 — indexed common food

Same as 214, prefixed with:

```
WriteByte(foodIndex)
```

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

- Exact **3-byte nutrition value scale** (library uses integer u24 via
  `encode_nutrition_value_u24`; float input uses `round(value)` unless a scale
  is supplied explicitly).
- **FFB4** icon file upload path.
- Delete payload confirmation on live HCI.
