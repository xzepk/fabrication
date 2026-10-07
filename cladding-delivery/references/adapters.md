# Adapter Contracts

## ACadSharp DWG helper

环境变量 `CADFAB_ACADSHARP_DUMP` 指向可执行文件。Skill 调用：

```text
<helper> inspect <drawing.dwg>
```

stdout 必须是 JSON，至少包含：

```json
{
  "adapter": "acadsharp",
  "file": "...",
  "entity_count": 123,
  "entity_types": {"Line": 100},
  "notifications": []
}
```

任何 reader notification 都必须保留，不能只输出成功状态。

## OCCT Provider

内置 provider，使用 CadQuery/OCP。只允许执行白名单工程操作；禁止执行模型生成的任意 Python。

当前白名单：

- planar plate solid + STEP/STL
- rectangular tube solid + STEP/STL
- planar plate 1:1 DXF flat pattern
- geometry metrics needed by BOM

## Rhino Provider

Rhino 不是硬依赖。若项目需要，配置外部工程 adapter：

- `CADFAB_RHINO_ADAPTER_URL`
- 可选 `CADFAB_RHINO_ADAPTER_KEY`

Skill 只调用受控工程接口，例如 `health`, `build-component`, `unroll-component`。外部 adapter 内部可使用 Rhino.Compute/RhinoCommon/Grasshopper，但 Skill 不直接持有 Rhino license token，不暴露任意 RhinoCommon 调用给 Agent。

如果 adapter 不可用，provider 必须明确失败；不得静默回落到不同几何内核并继续生产。

## Fabrication Adapter

凡是需要 K-factor、bend allowance/deduction、回弹、特定折弯机参数、焊接余量或机床 CAM 的构件，必须由项目/工厂验证过的 fabrication adapter 负责。内置 OCCT unfold 不宣称处理这些工艺。

## Nesting Adapter

内置 `builtin-shelf-review` 仅用于矩形板 REVIEW 排布和材料预估。生产套料应接入工厂认可的 nesting/CAM 软件或算法，契约至少返回 stock ID、板件 placement、旋转、利用率与未排入件。
