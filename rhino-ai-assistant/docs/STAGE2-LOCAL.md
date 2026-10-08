# Stage 2：首轮集成候选（单机）

本页补充 [WorkBuddy 主说明](WORKBUDDY.md)。目标是把本地结构化任务、选中受支持模型、独立 Skill、审阅交付包和 Rhino 预览串起来。**这是 Stage 2 首轮集成候选，不是完整单机包覆自动化、完整 Stage 2 验收或加工放行。**

Windows/Rhino 实机验证按用户决定 ON HOLD，验收值保持 NOT_RUN。真实本地模型未接入时，自然语言模型效果也是 NOT_RUN。模型 HTTP fixture、真实 Skill 子进程、SDK 编译和实机运行分别记录，不能互相代替。

真正日常通用工作流仍需另行设计：既有未受管来源的识别/接管、自动分板、复杂构造处理，以及实际 Windows/Rhino 与本地模型资格验证。本轮不补造这些能力，也不扩大未答复的方案范围。

## 1. 本轮支持范围

- 单机 Rhino 8.20/.NET 8 插件、认证 loopback Host，以及独立安装的 `cladding-delivery`。
- 保留 `cladding-delivery` 和 `cad-fabrication-engineering-v3` 的名称、目录、既有流程和独立运行能力。Harness 不合并它们，也不使它们依赖 Harness。
- 受管且经过形状验证的正交长方体可作为平板来源。支持 XY、XZ、YZ 三个板面，原点为世界包围盒最小点，宽/高在板面局部轴，厚度沿对应法向。
- 选中来源必须逐个映射为一块平板；这条路径不自动分板。每件 quantity=1，有独立原点与工程 ID，一批最多 128 件，仍受 Host 1 MiB 完整请求/快照大小限制；并非所有128件来源快照都一定装得下。输出 ID 与原来源 ID 分开保存，原来源不被删除。
- 任意 Brep、曲面、旋转板、方管、折边、孔槽、缺口、连接节点等都不在当前桥接能力内。**不会通过包围盒变成无孔实心矩形来掩盖缺失特征。**既有 Skill 能做某种几何，不代表这个 Rhino 桥接已完成对应资格验证。
- 材料、牌号、密度、尺寸、板面方向、复尺采用依据必须明确。不会根据“铝板”自行补充牌号或折边系数。
- 交付为 REVIEW：真实 STEP、审阅图纸、BOM、套料状态、标签映射及来源/版本/摘要清单。平板轮廓或几何套料不是折弯展开、CNC 文件或制造资格。制造始终 NOT_RELEASED。

## 2. 本地配置，不需要服务商与凭据

先按 WorkBuddy 主说明在获准环境构建。Host publish 目录携带固定的 `adapters/cladding/run.py` 等适配器文件；不要只复制 Host.exe 而遗漏其余输出。

仅在准备运行单机 Skill 时，为启动 Rhino/Host 的当前进程设置以下环境变量。路径须是绝对路径，由用户选择可信安装位置，不来自任务 JSON 或模型回答：

```powershell
$env:RHINOAI_CLADDING_PYTHON = 'C:\YourApprovedRuntime\Scripts\python.exe'
$env:RHINOAI_CLADDING_SKILL_ROOT = 'C:\YourRepo\fabrication\cladding-delivery'
```

独立 Skill 解释器要求 Python >=3.11,<3.15（主说明中的 Python3.10+ 仅指证据脚本）。解释器需要独立 Skill 的已安装依赖（CadQuery/OCCT、ezdxf、PyYAML、jsonschema）；以实际测试记录为准。安装依赖与启动候选仍按主说明的授权范围执行。没有配置时 Host 普通结构化工具仍可用，Skill 请求明确报告缺少配置。开发测试可通过 `RHINOAI_CLADDING_ADAPTER_ROOT` 指定仓库中的可信 `adapters/cladding` 目录；发布候选默认从 Host 旁固定目录读取。

自然语言入口可稍后接已有本地模型服务。没有模型时仍可手动填写任务并执行真实 Skill 流程。需要时设置：

```powershell
$env:RHINOAI_MODEL_ENDPOINT = 'http://127.0.0.1:8080/v1/chat/completions'
$env:RHINOAI_MODEL = 'your-local-model'
```

本轮只接受 literal IPv4 loopback 的这个路径，不接受远端/DNS/重定向/代理/认证信息。不会创建账号、索取密钥或代为下载模型。模型服务须支持文档中的兼容协议；未实际运行的服务不声称兼容。

## 3. 选中模型的自用流程

1. 在获准的新测试 3DM 中初始化 Harness，启动本地 Host。先确认单位为毫米，完成既有文档 QA。
2. 选择真正受支持的受管对象，选择板面方向，使用选中平板捕获入口。工具实际检查几何，不从任意模型的外包尺寸推定平板。
3. 在结构化任务 JSON 中检查每件来源、输出 ID、板面和尺寸；明确填写材料、牌号、密度。复尺采用值另列，保留设计/实测/采用值与采用依据。输入不完整时修正再运行。
4. 生成 REVIEW 交付包。Host 执行固定受限子进程、读回文件、核验摘要/快照和所需输出，完整验证后才原子提交新目录。失败运行不会冒充已完成结果。
5. 查看清单、警告和输出目录。单独执行平板批量预览，检查 detached 视口几何。文档、选择或输入变化后旧结果不能当作当前结果继续采用。
6. 明确接受这一次预览后才写入 Rhino，一个批次共用一个自有 Undo record。原来源保留，新增板件带工程身份和审阅包来源。Undo 只影响模型，不会删除已生成文件。

来源模型、复尺或规则变化后重新生成整包，不在旧目录中覆盖个别图纸/BOM。旧包保留为历史；“文件存在”不表示它仍对应当前模型。

## 4. 无模型服务的完整结构化路径

界面任务 JSON 可直接描述 `explicit_design`，或由选中模型捕获构建 `selected_managed`。后者要求每个来源 ID、指纹、尺寸与当前 detached snapshot 相符。缺失来源不得补成手填数据后仍称选中模型提取。

`examples/canopy-reference-task.json` 是可加载的 56 件雨棚名义表皮审阅任务；`examples/canopy-reference-plates.json` 还记录夹具来源、原 DWG/config SHA-256 和原配置的来源尺寸。它从既有参考配置离线生成，不构成两套 Skill 的运行时依赖。

该夹具包含 42 块 XY 顶板和 14 块 XZ 前檐。材料、表面处理、25 mm 折边等原有假设保留为警告；折边没有暗中建模。4130 mm 作为参考轮廓链保存，不能当作雨棚平面深度。夹具回归不等于实际 DWG 语义解析或实际 Rhino 选中模型验收。

## 5. 有本地模型时的受限规划

`/v2/plan` 至多发出一次模型请求，得到一个 clarification/tool/cladding.review 决策。模型看到受限的 detached 元数据和明确输入，不会收到整个 3DM、完整几何或对象属性文本。最多 64 个上下文对象、16 个选中对象；56 件雨棚的直接 Skill 路径不用经过这个规划入口。

模型不能执行脚本。尺寸、原点、ID、平移向量需能对应明确输入；缺少时询问，模型自行补值被拒绝。自由文本可使用明确字段，例如：

```text
创建盒体：width=100; depth=200; height=3; origin=(0,0,0); entityId=P-NEW
```

这些只是用户可输入的示例，不是系统默认工程参数。Skill 决策仍需完整、已审阅的平板任务，不让模型猜材料与构造。

`/v2/plan/validate` 给外部 agent 校验同一版本的决策契约，不调用模型、不写模型、不代替预览确认。外部 WorkBuddy 可以复用契约；本轮未实现远端 agent 账号或市场集成。

模型硬限制：4096 字 prompt、32 KiB 请求、64 KiB 响应、1024 输出 token、20 秒、禁止自动重试。Skill 是另外的有界进程，最多 300 秒，并限制 stdout/stderr、文件数量与产物总字节数。

## 6. 版本、证据与放行

- `Protocol.cs` 的基础工具协议与 `Planning.cs` 的 planner v2 分开版本化；以各 DTO 的字段及当前能力清单为准。
- `CladdingContracts.cs` 定义 review 请求、来源、工程值、清单和结果。每个包绑定输入快照、请求摘要、job ID、规则/Skill 版本和源码摘要、实体身份、产物 SHA-256。
- Host 在 prepare 和进入 Applying 前重新验证已存 review，不接受外部请求伪造一个摘要就绕过 Skill。
- 中文显示标签完整保留在可逆映射中，图纸使用 ASCII 工程 ID。没有最终像素检查不宣称中文字体通过。
- `scripts/release_gate.py` 仍检查 Stage 1；`scripts/stage2_gate.py` 检查组合 Stage 1/2，真实模型与实机证据缺失时返回 2/BLOCKED。开发可继续，门禁不会因此改成 PASS。

只有完成后续真实 Windows/Rhino、真实本地模型和工程审阅，才可升级相应资格结论。本轮不提供制造放行开关。


## 7. 从仓库复现测试

主构建脚本运行 Core、真实 Host HTTP、planner 协议 fixture、cladding 输入契约、门禁及 PowerShell 辅助测试。新增 `-SkillPython` 运行真正的独立 Skill 子进程、56件夹具及完整产物回读；不传时明确记录实际 Skill 流程 NOT_RUN，不能声称 Stage 2 全部通过。

```powershell
.\scripts\workbuddy-build.ps1 -SourcePath $Source -RunRoot $RunRoot -SkillPython 'C:\YourApprovedRuntime\Scripts\python.exe'
```

也可在构建后单独执行（使用新的证据目录）：

```text
dotnet tests/RhinoAi.Planning.Tests/bin/Release/net8.0/RhinoAi.Planning.Tests.dll <new-results-json> <dotnet-path> <Host-dll-path>
dotnet tests/RhinoAi.Cladding.Tests/bin/Release/net8.0/RhinoAi.Cladding.Tests.dll <module-root> <new-evidence-directory> <approved-skill-python>
python scripts/test_stage2_gate.py
python scripts/stage2_gate.py <actual-stage2-acceptance-json> --source-root <module-root>
```

本地模型兼容协议依据官方 [Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 与 [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) 文档核对，2026-10-08；只使用兼容消息传输与 JSON 对象响应，不声称特定本地服务已受验证或具有严格 schema 能力。Host 始终独立做严格校验。
