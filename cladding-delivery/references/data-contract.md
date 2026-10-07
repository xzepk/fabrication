# Canonical Data Contract

## Component

每个构件必须至少包含：

- `id`：稳定工程 ID；复尺/重算不得无故改变。
- `kind`：`panel` / `member` / `custom`。
- `geometry.type`：例如 `planar_plate`, `rect_tube`。
- `material`：材料、牌号、密度（若计算重量）。
- `quantity`：实例数量。
- `source.drawing_sha256`：原始图纸指纹。
- `source.entity_handles`：能够追溯时必须保留。

## 当前内置几何类型

### planar_plate

```json
{"type":"planar_plate","width_mm":1200,"height_mm":2400,"thickness_mm":3.0}
```

仅代表无折弯平面板。存在孔、折边、翻边、压筋、开槽或复杂轮廓时，应扩展 schema 并使用已验证的 project adapter；不得将其静默降级为矩形。

### rect_tube

```json
{"type":"rect_tube","width_mm":80,"height_mm":120,"wall_mm":4,"length_mm":3000}
```

## Survey

设计值、实测值、采用值必须同时保留。采用值必须有 evidence；复尺不能直接覆盖原始设计值。

## Stable labels and portable artifacts

`id` remains the exact original engineering identity (including Unicode) so survey references remain valid. `display_label` optionally preserves the human-facing label. Safe ASCII IDs `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` are retained unless Windows-reserved. Other IDs receive deterministic `C-<24 hexadecimal SHA256 characters>` machine IDs, derived from exact UTF-8 bytes. No transliteration or Unicode normalization is applied. Duplicate original IDs or case-insensitive filename collisions are errors. `label_map.json`, per-component `.identity.json` files and BOM columns preserve original IDs/labels alongside machine IDs. Only machine IDs appear in DXF TEXT and filenames.

Geometry providers accept only documented numeric fields and explicitly empty feature placeholders. Unknown fields or nonempty unsupported features block export rather than disappear. Optional/custom schemas do not expand provider capability. `effective_components.json` records the adopted survey dimensions used in that run; original design dimensions remain in the active source/snapshot.

The original `examples/components.json` is preserved; `examples/components-with-labels.json` separately demonstrates Chinese display labels.
