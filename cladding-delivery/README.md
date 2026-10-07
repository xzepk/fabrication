# cladding-delivery v3.0.0

工程包覆/幕墙深化 Skill，支持 Windows 与 Linux。默认几何链路为 **CadQuery → OCP → OpenCascade**，DWG 解析首选 **ACadSharp**；Rhino 仅是可选增强后端。

## 主流程

`DWG/DXF → canonical model → 方案确认 → 3D 深化预览 → 复尺 → 重算 → 展开/套料/BOM → REVIEW 交付包`

两个默认人工节点：范围/节点确认、现场复尺确认。任何环境或脚本成功都不自动等价于生产放行。

## 安装

推荐 Python 3.11–3.13：

```bash
python -m venv .venv
# Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -U pip
pip install -e .
```

`pyproject.toml` 已包含 CadQuery、ezdxf、PyYAML、jsonschema。

### 直接读取 DWG

需要 .NET 8 SDK 构建随包提供的 ACadSharp helper：

```bash
dotnet publish native/acadsharp-dump/ACadSharpDump.csproj -c Release
```

然后设置：

Linux:
```bash
export CADFAB_ACADSHARP_DUMP=/absolute/path/to/ACadSharpDump
```

Windows PowerShell:
```powershell
$env:CADFAB_ACADSHARP_DUMP="C:\path\to\ACadSharpDump.exe"
```

如果仅处理显式 DXF，可以不安装 .NET helper。

## 快速 Smoke Test

```bash
python scripts/run.py --project ./demo init
cp examples/components.json ./demo/work/components.json
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
