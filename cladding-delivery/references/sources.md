# 技术依据（2026-10-07 核对）

- ACadSharp: https://github.com/DomCR/ACadSharp — MIT，支持 DWG/DXF 读取；项目中使用独立 .NET helper 隔离解析 SDK。
- ACadSharp reading sample: https://github.com/DomCR/ACadSharp/blob/master/docs/articles/samples/reading.md
- CadQuery: https://cadquery.readthedocs.io/ — 无 GUI Python 参数化 CAD；底层使用 OCP/OpenCascade。
- cadquery-ocp: https://pypi.org/project/cadquery-ocp/ — OpenCascade Python bindings，提供 Windows/Linux wheels。
- OpenCascade Technology: https://dev.opencascade.org/ — 工业 CAD 几何内核。
- Rhino.Compute（可选增强参考）: https://developer.rhino3d.com/guides/compute/

本 Skill 不打包 Rhino、ODA、AutoCAD 或其他商业运行时。

- build123d official source: https://github.com/gumyr/build123d — optional deterministic geometry provider.
- build123d import/export: https://build123d.readthedocs.io/en/latest/import_export.html — STEP export and import, not manufacturing approval.
- text-to-cad/cadgen upstream: https://github.com/earthtojake/text-to-cad — evaluated as an external model-script/proposal workflow only; not installed or run in this change.

Version/platform claims must come from the current test report. Official upstream capability is not evidence that a local adapter or Windows runtime was exercised.
