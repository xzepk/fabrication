# cladding-delivery v3.1.0

工程包覆/幕墙深化 Skill，支持 Windows 与 Linux。默认几何链路为 **CadQuery → OCP → OpenCascade**，DWG 解析首选 **ACadSharp**；Rhino 仅是可选增强后端。

## 主流程

`DWG/DXF → canonical model → 方案确认 → 3D 深化预览 → 复尺 → 重算 → 展开/套料/BOM → REVIEW 交付包`

两个默认人工节点：范围/节点确认、现场复尺确认。任何环境或脚本成功都不自动等价于生产放行。

## 安装

使用 Skill 目录之外的 Python 3.11–3.13 虚拟环境。Linux 的 scripts/setup_linux.sh 和 Windows 的 scripts/setup_windows.ps1 都拒绝在包内创建 runtime。build123d 是可选 extra，cadgen 不安装、不执行。详见 references/operations.md。直接 DWG 的 .NET/ACadSharp helper 也必须在外部编译；DXF 和模型流程不需要 .NET 或 ODA。

## 受控模型能力

独立运行，不调用另一个 CAD Skill。OCCT 与 build123d 仅构造无孔无折边矩形板、尖角理想化开口矩形管。拒绝未支持字段；导出后真实 STEP 回读有效性、封闭边界、体积/面积、尺寸、位置及管件空腔探针。原始中文标签保留在映射/BOM 中，文件与 DXF 使用稳定 ASCII ID。

text-to-cad/cadgen JSON 可通过 proposal-import 暂存，审查后再显式 components-import。流程与边界见 references/providers.md。

## 快速 Smoke Test

```bash
python scripts/run.py --project ./demo init
python scripts/run.py --project ./demo components-import examples/components.json
python scripts/run.py --project ./demo doctor
python scripts/run.py --project ./demo snapshot
python scripts/run.py --project ./demo record scope --actor engineer --statement "demo scope confirmed" --evidence examples/demo-evidence.txt
python scripts/run.py --project ./demo run --mode preview
```

## 关键设计

- OpenCascade 是默认几何内核，不需要 FreeCAD。
- Rhino 不是前置依赖；若配置 `rhino` provider，则通过一个受控工程 API adapter 调用，不让 Agent 拼接任意 RhinoCommon API。
- 工程规则、CAD parser、Geometry Provider、Fabrication Provider 分层，方便后续替换或增强。
- 当前内置展开只针对经过验证的无折弯平面板；真正钣金折弯必须接入工艺规则。

这是 v3.1.0 本地 REVIEW 构建。Linux 回归与 Windows 实机验证必须分别报告；样例通过不表示制造放行。
