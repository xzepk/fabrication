---
name: cladding-delivery
description: Windows/Linux 工程包覆与幕墙深化总控 Skill。面向建筑包柱、包梁、幕墙铝板、金属装饰板等场景，将 DWG/DXF 解析、方案确认、参数化三维建模、复尺回填、板件展开、套料、BOM 和交付检查串成可追溯流程。默认使用 ACadSharp + CadQuery/OCP(OpenCascade)，Rhino 仅作为可选增强 Geometry Provider；不通过 UI 自动化控制 CAD 软件，不把未验证结果直接作为生产下单依据。
compatibility: Windows 10/11/Server or Linux; Python >=3.11,<3.15. Direct DWG parsing requires .NET 8+ and the bundled ACadSharp helper (or a compatible external adapter). CadQuery/OCP is the default geometry backend. Rhino is optional and is never a hard dependency.
metadata:
  version: "3.0.0"
  domain: "aec-fabrication"
  geometry-default: "occt"
---

# 工程包覆与幕墙深化总控

## Mission

把工程图纸转成可追溯、可重算的工程模型和 REVIEW 级生产资料。Agent 负责理解意图、编排和异常处理；确定性脚本负责几何、数量和文件生成；工程人员负责范围/节点确认与现场复尺。

固定主流程，不得跳过或重排：

1. **图纸解析**
2. **方案确认 — HUMAN GATE A**
3. **深化预览**
4. **现场数据回填 / 复尺 — HUMAN GATE B**
5. **生产文件生成**
6. **交付 — 可选 HUMAN GATE C / 下单审核**

## 核心架构约束

- 默认 Geometry Provider 为 `occt`：CadQuery → OCP → OpenCascade。
- `rhino` 仅为可选增强 Provider；没有 Rhino 时主流程必须仍可工作。
- 不依赖 FreeCAD、SheetMetal、ODA、AutoCAD UI 自动化。
- 直接 DWG 默认由 ACadSharp 适配器读取；DXF/ezdxf 为显式 DXF 或调试路径。
- Parser 和 Geometry Provider 必须通过 canonical schema 解耦；下游不得消费 SDK 私有对象。
- 任何 Rhino、OCCT、ACadSharp 或其他 CAD 内核都只是工具，不是工程规则的来源。
- 不允许模型自行臆造板厚、材料、节点、折弯参数、收口、缝宽、复尺值或生产公差。

## 当前实现范围

| 能力 | v3.0.0 状态 |
|---|---|
| Windows/Linux 项目初始化、doctor、快照、人工确认、断点运行、交付打包 | 已实现 |
| DWG 直接读取 | 已提供 ACadSharp .NET 8 helper 源码与适配器；需在目标环境构建 |
| DXF 清点 | 已实现 ezdxf adapter |
| canonical component/panel schema | 已实现 |
| OCCT Provider | 已实现基础平板、矩形型材建模与 STEP/STL 导出 |
| 平面板展开 | 已实现无折弯 planar plate 的 1:1 DXF |
| 基础矩形套料 | 已实现 REVIEW 级 shelf nesting；不可替代工厂 CAM 套料 |
| BOM | 已实现基础板件/型材理论量计算 |
| Rhino Provider | 已预留外部 adapter contract；默认禁用，不是硬依赖 |
| 双曲面自动分板、复杂 NURBS 展开 | 需项目专项规则/验证 |
| 通用钣金折弯展开、K-factor、回弹、机床 CAM | 未宣称通用实现；必须接入已验证 fabrication adapter |
| 自动生产放行 | 不提供；输出默认标记 REVIEW |

不要把脚本运行成功、OpenCascade 能力或样例测试通过表述成“大型项目已验收”。读取 `references/engineering.md`。

## 首选运行方式

将 `<skill>` 替换为当前 Skill 根目录，将 `<project>` 替换为独立项目目录：

```bash
python <skill>/scripts/run.py --project <project> init
python <skill>/scripts/run.py --project <project> doctor
python <skill>/scripts/run.py --project <project> inspect <drawing.dwg>
# 经项目映射/专项解析得到 canonical components 后导入；不可凭空生成生产尺寸
python <skill>/scripts/run.py --project <project> components-import <components.json>
python <skill>/scripts/run.py --project <project> snapshot
python <skill>/scripts/run.py --project <project> record scope --actor '<实际确认人>' --statement '<范围/材料/节点/分板确认>' --evidence <evidence-file>
python <skill>/scripts/run.py --project <project> run --mode preview
```

复尺后：

```bash
python <skill>/scripts/run.py --project <project> survey-import <survey.yaml>
python <skill>/scripts/run.py --project <project> snapshot
python <skill>/scripts/run.py --project <project> record scope --actor '<实际确认人>' --statement '<复尺后修订范围确认>' --evidence <evidence-file>
python <skill>/scripts/run.py --project <project> record survey --actor '<实际复尺确认人>' --statement '<复尺结果确认>' --evidence <evidence-file>
python <skill>/scripts/run.py --project <project> run --mode remeasured
python <skill>/scripts/run.py --project <project> verify --run-id <run-id>
python <skill>/scripts/run.py --project <project> package --run-id <run-id>
```

## 每次任务的执行规则

1. 先判断首次项目、续跑、复尺变更还是专项算法接入；已有项目不得重新初始化或重编板号。
2. 保留原始 DWG/DXF，不覆盖输入；记录 SHA256、解析器版本和所有阻断警告。
3. `doctor` 必须先验证 Python、CadQuery/OCP、DXF adapter、ACadSharp helper（若处理 DWG）和当前 Geometry Provider。
4. DWG 解析发生不支持对象、proxy、XRef、字体、动态块或异常通知时，必须进入 `issues.json`，不得静默丢弃。
5. 从图纸到工程对象的语义映射必须有来源证据。v3.0.0 内置 DWG helper 负责清点，不宣称自动理解所有构件；使用项目映射/专项解析器形成 canonical components 后再 `components-import`。图层/块名可作为证据，但不能作为唯一真值。
6. HUMAN GATE A 必须覆盖包覆范围、材料/厚度、节点、分缝/分板、必要加工规则及假设。
7. 预览允许生成模型、工程预览、初步 BOM 和异常报告；不得标记为生产放行。
8. 复尺值要与设计值并存，记录采用值和依据。复尺变化必须使受影响下游产物失效并重算。
9. `remeasured` 模式同时要求当前快照有效的 `scope` 与 `survey` 确认。
10. 输出的 STEP/DXF/BOM/套料结果都要进入 run manifest，并记录 provider、版本、输入快照和 REVIEW 状态。

## Geometry Provider 选择

默认配置：

```yaml
geometry:
  provider: occt
  units: mm
  absolute_tolerance_mm: 0.1
```

`occt` 必须优先用于普通平板、规则型材和已验证参数化构件。只有当项目明确需要并配置了外部 Rhino adapter 时，才允许：

```yaml
geometry:
  provider: rhino
```

Rhino provider 契约见 `references/adapters.md`。Skill 不保存 Rhino 商业授权，不调用 Rhino UI，也不直接把 LLM 生成的任意 RhinoCommon 调用发送给服务端。

## 错误与阻断

- 退出码 `0`：命令完成，不等于制造许可。
- 退出码 `2`：业务阻断，例如未确认、当前快照变化、几何类型不支持、缺失复尺。
- 退出码 `1`：程序或环境错误。

遇到不支持构件时：保留已完成部分，输出板号/构件号、阻断原因、所需资料和推荐 adapter；禁止偷偷退化为矩形板或忽略孔/折边。

## 按需读取

- `references/architecture.md`：模块边界与数据流。
- `references/data-contract.md`：canonical component/panel 数据约定。
- `references/adapters.md`：ACadSharp、OCCT、Rhino、fabrication、nesting provider 契约。
- `references/engineering.md`：工程精度、展开、验收边界。
- `references/operations.md`：Windows/Linux 安装、恢复、批处理。
- `references/sources.md`：依赖与官方资料依据。
- `config/project.example.yaml`：默认项目配置。
- `examples/components.json`：可运行的基础构件样例。

## 发布前检查

```bash
python <skill>/scripts/validate_skill.py <skill>
PYTHONPATH=<skill>/src python -m pytest -q <skill>/tests
python <skill>/scripts/run.py --project <temp-project> init
python <skill>/scripts/run.py --project <temp-project> doctor
```

Skill 包中不得包含 Rhino、ODA 或其他不可再分发商业运行时/许可证文件。
