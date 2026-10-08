# WorkBuddy：从仓库构建 Rhino AI 单机候选并做实机验收

文档日期：2026-10-08（UTC）  
适用对象：可读取仓库、操作 Windows 桌面、运行 PowerShell 的 WorkBuddy 或其他 agent。  
当前状态：**REVIEW；Windows/Rhino 实机验收 NOT_RUN；完整 Stage 1 门禁 BLOCKED。**

本文是仓库自包含的主入口。只需要 [fabrication 仓库](https://github.com/xzepk/fabrication) 的可信 clone 或 GitHub 源码归档，不依赖聊天附件、Library、旧交接 ZIP、另一位助手的磁盘或预编译候选。`.rhp` 和 Windows Host 在获准的 Windows 测试机本地构建；仓库不提交这些二进制。

本文提供未来的执行说明。**本次仓库文档/脚本交付本身不授权安装软件、运行候选程序或操作用户电脑。** 先按第 2 节确认执行范围。构建成功、能加载插件、基础冒烟通过和完整技术验收通过，是四个不同结论。

## Stage 2 本轮增量与 Windows 暂缓

2026-10-08 用户决定当前没有 Windows 环境，先暂缓实机验证并推进单机自用实施。开发继续不修改 F/L 实机验收结果：仍为 ON HOLD / NOT_RUN，完整技术与生产放行保持 BLOCKED。

新增路径、环境配置、选中受支持模型、自然语言/结构化任务、56 件雨棚名义表皮夹具、同快照审阅产物及明确边界见 [Stage 2 单机自用](STAGE2-LOCAL.md)。本页下文保留 Stage 1 安全基础与未来 Windows 操作步骤。当前源码可含 Stage 2 实施候选，不能把下文历史 Stage 1 限制表误读为最新功能列表；实际能力以本节及受支持 DTO/能力清单为准。

构建脚本另外运行 planner 的真实本地 HTTP fixture 测试及 Stage 2 gate 测试，publish 携带固定 Skill 适配器。它们不证明真实模型已运行，也不证明 Windows/Rhino 已运行。真实独立 Skill 与56件夹具另按增量测试入口记录；缺依赖即 NOT_RUN，不用空壳模拟替代。

## 0. 可以直接交给 WorkBuddy 的任务模板

> 请从 https://github.com/xzepk/fabrication 的 rhino-ai-assistant/docs/WORKBUDDY.md 开始。使用我已有的仓库访问权限，取得本轮实际提交的源码，并记录完整 commit。没有 Git 时可用该提交的 GitHub 源码归档。不要依赖任何聊天 ZIP 或创建 token。
>
> 先做只读预检，说明将使用的源码、脚本、Windows/Rhino 实例、新测试目录和备份。获得本轮本地构建、候选执行/插件加载和新建测试模型常规验收的许可后，再运行仓库原生 PowerShell 脚本。候选二进制生成后核对清单，在首次加载前展示确切路径与哈希。软件安装、UAC、安全拦截、配置变化和受控故障注入需按实际范围另行确认，不绕过防护。
>
> 只在真正新建的空白测试 3DM 中测试 Box、平移、预览/取消、原生 Undo/Redo、保存重开和 managed checkpoint restore。先让我确认是否允许覆盖本轮自行创建的受管测试对象；范围明确获准后，可以在该范围内操作 UI 确认。不打开、不覆盖生产 DWG/3DM，不改源码，不推送仓库，不上传模型或日志，不创建账号/凭据。
>
> 为 L-01～L-20 和 F-01～F-12 分别记录 PASS / FAIL / BLOCKED / NOT_RUN、子项、原因和证据。缺少调试器或可靠注入能力时，将 L-15、L-16、L-18 及其他无法精确观测的时序分支记 BLOCKED，继续能安全执行的普通 GUI 验收。不得删除 journal、重初始化失败文档或改结果来解除隔离。
>
> 最后交回本轮来源、版本、自动化日志、逐项 live 结果、截图、测试模型、operation/checkpoint、哈希清单、acceptance.local.json 和门禁原始输出/退出码。可以报告“基础冒烟通过，完整验收仍受阻”。仅全部必要断言真实通过且门禁返回 0 时，才报告 Stage 1 技术验收通过；生产状态始终 REVIEW。

任务模板只有在用户实际发出并确认所需范围后才构成执行授权。

### 最短阅读路线

1. 第 1～3 节：取得源码、确认权限、记录本轮来源。
2. 第 4～5 节：环境预检、本地 build/test/publish；生成独立运行目录。
3. 第 6～7 节：插件加载、Host 配对和普通 GUI 冒烟。
4. 第 8～10 节：完整 L/F 覆盖、证据、fail-closed 门禁。
5. 第 11～12 节：交回结论和安全退出。

### 完成定义与范围

- 安装可用：真实 Windows Rhino 加载 `.rhp`，停靠/浮动 UI 均能打开，独立 Host 完成认证连接。
- 基础闭环可用：实际观察预览/取消、一次提交、100 mm Box、100 mm X 平移、Undo/Redo、保存重开及受管恢复，并保留证据。
- 报告完整：20 条 L 与 12 个 F 各有状态；没有执行的分支也要列出。
- 技术通过：F-01～F-12 全部符合 [SPEC.md §37](../SPEC.md#37-acceptance-matrix)，相关 L 子项通过，证据、源码摘要和环境有效，门禁返回 0。否则完整验收保持 BLOCKED。
- Stage 1 基础测试不覆盖 Stage 2；当前新增的受限本地规划/平板 Skill 审阅路径见上节。通用建模、复杂构造、任意代码执行、通用 Revert/历史合并或生产下单仍未实现。

## 1. 仓库来源与固定环境

### 1.1 唯一源码入口

- 仓库：<https://github.com/xzepk/fabrication>
- 模块：`rhino-ai-assistant/`
- 主操作说明：`rhino-ai-assistant/docs/WORKBUDDY.md`
- 构建入口：`rhino-ai-assistant/scripts/workbuddy-build.ps1`
- 本轮验收入口：`rhino-ai-assistant/scripts/workbuddy-verify.ps1`

使用用户既有、已授权的 Git/GitHub 登录。权限不足时让用户通过自己的登录界面恢复访问或从同一仓库下载所选提交的源码；不要索取密码/token，不创建 PAT、SSH key 或额外 OAuth 授权。归档也必须来自可核验的仓库提交；来历不明的 ZIP 不可作为替代。

### 1.2 版本和环境

| 项目 | 本轮要求 |
|---|---|
| 系统 | Windows x64；ARM64/模拟执行不在初始资格范围 |
| Rhino | 合法授权的 Windows Rhino 8，初始目标为 **8.20 / .NET 8**；记录完整 build |
| 更高 Rhino 8 SR | 代码允许 8.20 以上，但每个新 build/runtime 组合仍需单独实机资格验证 |
| 不支持的实机组合 | Rhino 7、macOS/Linux Rhino、.NET Framework、其他 .NET 主版本 |
| 构建 SDK | `global.json` 固定 .NET SDK **8.0.425**，`latestPatch` 只允许同一 feature band 内 patch；记录实际选中版本 |
| Host runtime | Windows x64 `Microsoft.NETCore.App 8.0.x` 与 `Microsoft.AspNetCore.App 8.0.x`；Rhino 自带 runtime 不能证明系统 ASP.NET runtime 已存在 |
| Python | Python 3.10+；脚本自动寻找 `py -3` 或 `python`，也可显式传入解释器路径 |
| Rhino 编译引用 | 官方 NuGet `RhinoCommon [8.20.25147.11001-rc]` 与锁定的 Eto 等依赖；这是编译引用，不是已在 RC 上运行的证据 |
| 输出 | Host 为 `win-x64`、framework-dependent；插件为 `net8.0-windows` 的 `.rhp` |

所有 restore 使用 locked mode。不要删除/重写 lock 文件、换 SDK 主版本或使用假 Rhino SDK 来“构建成功”。RhinoCommon、Rhino.UI、Eto 是 Rhino 提供的运行依赖，不复制进候选 plugin 目录或 Rhino 系统目录。

缺少软件时，停止对应分支并说明拟安装的软件、官方来源和权限要求。由用户决定是否安装；Rhino 许可/登录由用户处理。官方入口：[.NET 8](https://dotnet.microsoft.com/en-us/download/dotnet/8.0)、[Python Windows](https://www.python.org/downloads/windows/)、[Git for Windows](https://git-scm.com/downloads/win)。

### 1.3 区分本轮来源与历史证据

`SOURCE_BASELINE.json` 记录早期 SPEC 基线，**不能当作当前实现的 checkout commit**。`evidence/acceptance.json`、原 build/test 日志、原 `source-manifest.json` 和其中的 LOCAL_ONLY/未安装说明，是其生成时的历史记录。后续仓库发布不会把历史 Linux 结果变成 Windows 实机结果。

本轮必须单独记录：实际 `git HEAD`（或 GitHub 源码归档对应的完整 commit）、来源获取方式、工作树是否有修改、本轮源码逐文件清单/聚合 digest、实际构建产物哈希和实际运行版本。不要把本说明中的日期、旧基线或某个旧摘要当作本轮值。未来提交不会预先写死在本文。

## 2. 权限与安全边界

- 只读仓库/环境检查可以先做。运行构建脚本、测试进程、候选程序集或注册/加载插件前，确认本轮执行许可；有授权的常规测试不必逐按钮重复询问。
- 使用普通用户权限。未知发布者、UAC、SmartScreen、ExecutionPolicy 或其他安全阻拦出现时，记录真实提示并停在该步。不要自行 `Unblock-File`、`Set-ExecutionPolicy`、使用 `-ExecutionPolicy Bypass`、关闭防护或绕过浏览器安全警告。
- 不安装/购买 Rhino，不绕过许可，不改全局模板、生产项目、系统 SDK DLL、防火墙/VPN/代理或凭据。Host 只监听 literal `127.0.0.1`；不授权公网监听。
- 只操作新测试目录、已批准的 Rhino 实例及真正新建测试文档。不用全局 `taskkill /IM Rhino*`，不终止其他同名进程。
- Restore 覆盖**所有当前受管对象及其后续人工/AI 编辑**，同时应保留非受管对象。逐次审查 checkpoint、文档和范围。只在已批准的本轮测试范围内接受；涉及原有编辑/文件时重新确认。
- nonce 由 **Start local host** 生成并经子进程私有环境传递，不需要手动生成、复制或在聊天中提供。不要打印完整进程环境、Bearer header、nonce、内存 dump 或未脱敏网络抓包。
- 模型/日志/报告保存在约定本地目录并交给用户。上传到仓库、在线分析服务、其他 agent 或云盘需要另外明确授权。包含其他项目记录的 Host journal 不能整库外传。
- `Applying`、`FailedRecovery`、`recovery-required`、`lineage-block` 或不确定结果出现后，停止该文档的 agent 写入，保留现场。禁止删除 journal/lock/marker、清空 LocalAppData、重新初始化失败文档、循环 Commit 或自动 Restore 来掩盖失败。

## 3. 取得源码并建立本轮身份

两种路径任选其一。以下 PowerShell 示例中的真实目录可由用户指定；不要执行未替换的 `<...>` 占位值。每次测试使用新目录，不覆盖旧报告。

### 3.1 Git clone（首选）

在既有授权可用的终端运行。`clone -c core.autocrlf=false` 只配置这次新 clone，防止 Windows 自动换行转换使文件字节与源码清单不同，**不改全局 Git 配置**。

```powershell
$ErrorActionPreference = 'Stop'
$Work = Join-Path $env:USERPROFILE 'RhinoAI-WorkBuddy-Test'
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$Repo = Join-Path $Work ('fabrication-' + $RunId)
if (Test-Path -LiteralPath $Repo) { throw '目录已存在，请使用新的目录。' }
New-Item -ItemType Directory -Path $Work -Force | Out-Null
git clone -c core.autocrlf=false https://github.com/xzepk/fabrication.git $Repo
if ($LASTEXITCODE -ne 0) { throw '仓库读取失败；使用已有授权处理，不创建或索取凭据。' }
$Source = Join-Path $Repo 'rhino-ai-assistant'
$ActualCommit = (git -C $Repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw '无法记录本轮 commit。' }
git -C $Repo status --short
if ($LASTEXITCODE -ne 0) { throw '无法核验工作树。' }
$ActualCommit
```

这会取得当时默认分支的实际 HEAD。若用户指定了另一提交，先用既有权限获取并 `checkout --detach` 该完整 commit，再记录实际 HEAD；之后不再 `pull`。先确认该提交确有本文和两份原生脚本。若模块工作树不是干净状态，记录差异并停止构建，重新取得干净源码或让用户确认其来源；不要清理用户的修改。

### 3.2 GitHub 源码归档（无 Git 时）

1. 在用户已有登录的 GitHub 中打开上述仓库，选定含本文的目标提交，记录页面显示的完整 commit。
2. 从该提交的源码页面下载源码 ZIP。不要只记可移动的分支名；如果下载的是分支归档，必须另核实其准确提交，否则来源记 BLOCKED。
3. 将 ZIP 解压到全新本地目录。记录原 ZIP 路径、字节数、SHA-256、所选完整 commit 和仓库 URL。ZIP 文件名里的简称不足以单独证明来源。
4. 将 `$Source` 指向解压后实际的 `rhino-ai-assistant` 模块目录；验证其中有 `RhinoAi.sln`、`global.json`、`src`、`scripts/workbuddy-build.ps1`。不要求文件夹必须叫 `fabrication-main`。
5. 通过 `-SourceCommit $ActualCommit` 将已核实的归档完整 commit 传给第 5 节 build 脚本，报告里明确 `source acquisition = GitHub source archive`。没有 `.git` 时不伪造 git HEAD；将用户核实的归档 commit 单独记入来源证据。

```powershell
# 将此值替换为解压后的真实模块路径。
$Source = 'C:\Users\<用户>\RhinoAI-WorkBuddy-Test\fabrication-<提交>\rhino-ai-assistant'
$ActualCommit = '<从GitHub核实的40位完整commit>'
if ($ActualCommit -notmatch '^[0-9a-fA-F]{40}$') { throw '先填入已核实的归档完整 commit。' }
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
```

### 3.3 源码完整性与目录解析

原生入口的 `-SourcePath` 可接收仓库根目录、模块根目录，或包含单个解压仓库的父目录。若探测到多个候选模块，不要猜测；传入已核实的确切模块路径。本文后续 `$Source` 始终表示实际模块根目录。

本轮 `RunRoot` 必须是模块内 `artifacts/workbuddy-runs/` 下的**新唯一目录**。这样结果不进入 Git，门禁仍可按模块内相对路径检查证据。不要把 RunRoot 放在模块外、`src/` 或历史 `evidence/` 下，不预先创建它，不重复使用一次失败/部分生成的目录。

构建脚本先比较已提交的 `evidence/repository-workflow/source-manifest.json`，通过后记录本轮源码清单和摘要；验收脚本复核它们及候选文件。路径规范使用 `/` 和与 OS 无关的 ordinal 排序，避免 Windows/Linux 路径排序不同；文件 SHA-256 比较的是原始字节，因此 LF/CRLF 变化仍是源码变化。缺文件、新增源文件、改字节或候选被替换时必须阻断，不能更新期望值来掩盖差异。

清单把仓库源码、本轮 build 和后续 live evidence 绑定到同一候选，但不能独立证明来源可信，仍需本节的 Git/归档 commit 核实。与已提交的新工作流清单不符时停止，不刷新期望值；先保留差异，再重新取得指定提交且保持原始换行。旧 `evidence/source-manifest.json` 是历史构建记录，保留原样，不用于放行当前候选。

## 4. 预检、备份与证据计划

### 4.1 先确认，不变更系统

- 查看 Windows 版本和 x64 架构。运行现有 `dotnet --info`、`dotnet --list-sdks`、`dotnet --list-runtimes`；从模块目录运行 `dotnet --version`，确认 `global.json` 实际选中 SDK。用 `py -3 --version` 或 `python --version` 确认 Python。
- 必须确认系统有 x64 的 `Microsoft.NETCore.App 8.0.x` 和 `Microsoft.AspNetCore.App 8.0.x`。仅装 Desktop Runtime、或 Rhino 能启动，都不足以证明 Host 运行条件。
- 在 Rhino“关于”和 `_SystemInfo` 中保存完整 build、位数、当前进程 runtime。使用 [SystemInfo 的 Save As](https://docs.mcneel.com/rhino/8/help/en-us/commands/systeminfo.htm)保存文本；外部 `dotnet --info` 不能证明 Rhino 进程使用 .NET 8。
- Rhino 8.20 默认 .NET 8，但仍实测。若需切换，按 [McNeel runtime 指南](https://www.rhino3d.com/en/docs/guides/netcore/)先说明并获准。`SetDotNetRuntime` 区分 Core/Framework；主版本也要确认。官方 `/netcore-8` 可限定一次启动，可能需要已安装的 x64 .NET Desktop Runtime。记录原设置与重启前状态；不猜注册表设置。
- 检查已有 Rhino AI 插件注册路径、运行实例、`%LOCALAPPDATA%\RhinoAi` 数据和 Host 归属。默认 Host journal 固定在 LocalAppData，不在 RunRoot；它可能包含原有历史。发生单写锁/已有实例冲突，记录 BLOCKED 并让用户决定隔离工作站或停止所属测试实例，不能删锁抢占。
- 业务文件不参与。无关文档如何保存/关闭由用户决定。故障测试只用专用实例；采用独立 Windows 测试账号/工作站也须已有或另获授权，不擅自创建账号。

### 4.2 最小证据

构建后在 `$Evidence`（第 5 节）下创建 `environment`、`cases`、`screenshots`、`models`、`journals`、`checkpoints` 子目录。每条 `cases/L-xx.md` 记录：UTC 时间、操作者、前提、每个子项步骤/状态、期望与实际、Document/Session/Operation ID、Rhino GUID/工程 ID、截图、before/after 3DM、journal/checkpoint 和阻塞。

- `PASS`：整行全部子项实际执行且证据符合要求。
- `FAIL`：已执行且观察到缺陷。不能改成 BLOCKED 掩盖回归。
- `BLOCKED`：具体权限、软件、测量/注入能力不足；写清需要什么。
- `NOT_RUN`：尚未执行。部分完成只能给子项状态，不能给整行 PASS。

截图不能单独证明 Undo 记录数、属性相等或“零变更”。结合对象属性、几何测量、journal 的 added/modified/deleted 数组、before-image/checkpoint。无可靠观察方法的断言记 BLOCKED。3DM 文件哈希用于证据完整性，不能作为几何不变的唯一判断，因为保存元数据也可能改变字节。

## 5. 原生 PowerShell 构建、自动化与候选

获得第 2 节执行许可后，在普通 PowerShell 中逐段运行。不要为了运行脚本关闭执行策略。若当前策略阻止脚本，报告实际提示并由用户决定合规处理方法。

```powershell
$RunRoot = Join-Path $Source ('artifacts\workbuddy-runs\' + $RunId)
if (Test-Path -LiteralPath $RunRoot) { throw '本轮目录必须全新；请换 RunId。' }
& (Join-Path $Source 'scripts\workbuddy-build.ps1') -SourcePath $Source -RunRoot $RunRoot -SourceCommit $ActualCommit
$BuildExit = $LASTEXITCODE
if ($BuildExit -ne 0) { throw "构建/自动化受阻，退出码 $BuildExit；保留本轮日志，不加载候选。" }
```

可选显式工具路径：

```powershell
& (Join-Path $Source 'scripts\workbuddy-build.ps1') -SourcePath $Source -RunRoot $RunRoot -SourceCommit $ActualCommit `
    -Dotnet 'C:\Program Files\dotnet\dotnet.exe' `
    -Python 'C:\Users\<用户>\AppData\Local\Programs\Python\Python313\python.exe'
```

这两段是二选一，不能对同一 RunRoot 执行两次。Git clone 路径的实际 HEAD 可被脚本读取；显式 `-SourceCommit` 必须与它一致。归档路径没有 `.git`，必须提供已核实的 `-SourceCommit $ActualCommit` 才能形成完整来源记录；未知来源不允许完整验收放行。路径必须已存在且来源可信；省略参数时自动发现本机 `dotnet`、`py -3` 或 `python`。不要把 `py -3` 整段字符串当作 `-Python` 的文件路径。

构建流程应完成 locked restore、Release build、Core fake-adapter 回归、真实 Host HTTP 进程测试、门禁/证据工具回归、PowerShell 自检，以及 Host `win-x64 --self-contained false` publish 和插件收集。任一步失败都保留日志并停下；禁止旧产物回填、忽略退出码或改 lock。

本轮目录包含候选、日志、来源/产物清单与 `acceptance.local.json`。只使用脚本明确报告的路径；不要从旧的 `bin/obj` 或另一次 run 拿二进制。

```powershell
$Candidate = Join-Path $RunRoot 'candidate'
$Evidence = Join-Path $RunRoot 'evidence'
foreach ($name in @('environment','cases','screenshots','models','journals','checkpoints')) {
    New-Item -ItemType Directory -Path (Join-Path $Evidence $name) -Force | Out-Null
}
```

加载前核实 `candidate/plugin/RhinoAi.Plugin.rhp` 与旁边的 `RhinoAi.Core.dll`、`RhinoAi.Contracts.dll`、`RhinoAi.Plugin.deps.json`，以及 `candidate/host/RhinoAi.Host.exe` 的产物清单。保留完整 host 文件夹；framework-dependent apphost 不能单独复制成一个 EXE。不要把 RhinoCommon、Rhino.UI、Eto DLL 塞进插件目录。

保存实际 SDK/runtime、构建与测试退出码、源码摘要、完整 commit/归档出处和候选哈希。自动化只覆盖 F-01/F-12，**不会替你操作 Rhino、授权安装、完成 L 用例或把 F-02～F-11 标 PASS**。即使本轮自动化全绿，首次门禁仍应 BLOCKED。build 脚本退出 0 只表示构建/自动化成功；它会另存初始 gate 的实际退出码（预期 2）到 `build-result.json`，不能把这两个退出码混为一谈。

## 6. 在 Rhino 中加载并连接

1. 使用专用测试 Rhino 实例。按照 [Rhino 官方加载说明](https://www.rhino3d.com/en/docs/guides/scripts-plugins/how-to-use/)，可运行 `_PlugInManager` 打开插件管理器，然后选 **Install** 加载对应的现有 `.rhp`。不同语言/服务版本显示以实际界面为准；不要猜其他安装命令。
2. 文件：`$Candidate\plugin\RhinoAi.Plugin.rhp`。依赖仍保留在旁边。记录插件名称、路径、加载状态和任何警告。
3. 在 Rhino 命令行分别运行已在源码声明的 `RhinoAiPanel`、`RhinoAiFloat`。停靠面板标题 `Rhino AI Harness`，浮窗标题 `Rhino AI Harness · Stage 1 candidate`。各截图一张。
4. 在任一面板点击 **Browse…**，选 `$Candidate\host\RhinoAi.Host.exe`。`Loopback endpoint` 保持 `http://127.0.0.1:47831/`，点击 **Start local host**。
5. 验证显示 `Connected to http://127.0.0.1:47831/`（端口以实际为准）及 Host started 状态。两个 UI 共享同一全局 Host，不在另一 UI 再启动第二个。另一面板的连接文字可能未自动刷新；不能只根据那一行判定真实连接。
6. 此路径自动生成短期 nonce，仅通过子进程私有环境传递，**无需填写/复制密钥**。不要在浏览器打开 health 来“验证登录”：所有路由需要认证，裸访问 401 本来就可能正确，服务没有浏览器 UI。
7. 端口冲突时只查看占用者，不终止不属于本轮的进程。未建立连接前可选空闲的非特权端口（1024～65535），保持 literal `127.0.0.1` 并记录；Host journal 单写锁与端口是两个独立约束。
8. 本常规路径不使用 **Attach host**。它是给已按 host runbook 启动且可安全配对的 Host 使用，nonce 掩码并即刻清空，不应写入脚本、URL、文件或日志。若测试必须走 Attach，另列受控方案与许可，不通过读取进程内存窃取 nonce。

**真实 UI 限制：**当前没有 `Stop host`、`Disconnect`、`Reconnect` 或故障注入按钮；不要编造。Host 被杀后，现有 Rhino 进程中的静态 client 仍可能存在，直接再次 Start/Attach 会得到 `host-connected`。L-17 重连需要受控计划，不能用一句“点重新连接”替代。完整关闭该测试 Rhino 才会调用插件 shutdown 并清理其自有 Host；先保存与记录。

## 7. 先执行的基础实机场景

### 7.1 空文档和“读取不能偷偷初始化”

- 新建**空白** Rhino 文档，只在该文档设置 Millimeters 和 absolute tolerance `0.01`。保存为 `$Evidence\models\smoke-before.3dm`；原始业务文件完全不参与。
- 初始化前分别点 **Inspect context** 和 **Preview box**。预期 `document-uninitialized`，没有对象、没有 `RhinoAi.DocumentId` 新元数据、没有插件新建的 Undo 记录。保留前后对象/属性/Undo 观察。若无法观察元数据或 Undo，记录相应子项 BLOCKED。
- 点击 **Initialize document** **一次**。此明确动作会写持久文档 ID，并有自己的初始化 Undo 记录；不要把它误算成 Preview 的副作用。保存测试 3DM 以持久化 ID。
- 点击 **Inspect context**：应记录 Document、Session、Revision、Units `Millimeters`、tolerance `0.01`、managed objects `0`、QA。若不是这些值，停止并查真实文档设置。

### 7.2 Preview / Reject / 创建

保持 UI 字段：

| UI 字段 | 值 |
|---|---|
| Engineering ID | `BOX-001` |
| Origin X, Y, Z | `0, 0, 0` |
| Width, depth, height | `100, 100, 100` |
| Translation X, Y, Z | `100, 0, 0` |

数字使用英文逗号与小数点。

1. 点击 **Preview box**，观察蓝色 detached conduit。对象表仍为 0 个受管对象，未创建 Box，Preview 不开启模型 Undo。
2. 点击 **Cancel preview**，蓝色消失；对象、几何、属性、文档 ID 不变。保留操作 ID、局部 journal 的 Cancelled 结果及 Host 对应结果。按钮叫 Cancel preview，协议还存在 Rejected 枚举；不要强行把实际 Cancelled 改名为 Rejected。
3. 再次 **Preview box**，记录新的 operation ID。点击 **Accept preview & commit**，审查标题 **Accept preview** 的 summary、Document、Operation。只接受当前测试文档/精确 Box 请求，确认后检查实际结果。
4. 预期仅一个实心 Brep Box，包围盒 `(0,0,0)` 到 `(100,100,100)`，尺寸各 100 mm，体积约 1,000,000 mm³（采用合理测量容差）。managed count 从 0 到 1；工程 ID 是 `BOX-001`，Rhino GUID 非空。
5. 观察 `Committed locally and durably`、非零 owned Undo record 和 `Host acknowledgement recorded`。journal 应有正确 before-image、added 一项/modified 零项/deleted 零项、对应 task/operation/provenance。单个提交只占自己一个语义 Undo 记录；初始化记录另计。不能只凭“看见一个盒子”通过 F-04。

### 7.3 平移、选择规则与 Undo/Redo

- 用无选择、选非受管对象、多选分别尝试 **Preview selected managed box move**，应拒绝且不变更。再准确选择 `BOX-001` 一个对象。
- `Translation X, Y, Z = 100, 0, 0`，点击 **Preview selected managed box move**，观察 `(100,0,0)` 到 `(200,100,100)` 的预览。审查并 **Accept preview & commit**。
- 原 Rhino GUID、工程 ID 保持；modified 数组恰好该 GUID 一项，没有额外 add/delete；尺寸和体积不变，实际 X 位移 100 mm。
- 使用 Rhino 原生 Undo，再 Redo，每次 **Inspect context**。几何跟随 Rhino，工程 ID 正确，revision 更新，旧预览失效，Host 不为了“恢复已提交”自动再移一次。
- Inspect UI 只直接列出受管 entity ID/GUID，没有任意选择列表或全部 snapshot hash 显示。选择目标要通过操作 request.objectId 与实际选择交叉核验；完整快照从 journal/checkpoint 查看，不能编造 UI 字段。

### 7.4 Checkpoint 与非受管保留

1. 确认当前受管状态干净且 QA 无问题，点 **Save managed checkpoint**。记录 checkpoint ID、文件和哈希。默认下拉显示时间/对象数/ID，不弹出自定义命名输入框。
2. 在正常当前状态中分别测试后续 add / move / delete，使用 `BOX-002` 等唯一 ID；同时用 Rhino 原生命令创建一个非受管对象，例如距盒子很远的线段，确认没有 `RhinoAi.EngineeringEntityId`。记录其 GUID、几何、属性。
3. **Refresh checkpoints**，按确切 ID 选择原 checkpoint，点 **Preview managed restore**。检查显示的是保存时的受管范围。
4. 点击 **Accept preview & commit** 会出现 **Accept managed-scope restore**。它要替换所有当前受管对象和其后续编辑，不重建全 3DM/表结构。若本次覆盖已在开工时获准的专用测试范围内，agent 可接受该 UI 确认；否则选 No 并询问。选 No 后仍可 **Cancel preview**，不能把 No 当已恢复。
5. 在获准范围内接受 UI 确认后，验证受管对象集合、几何、完整属性、工程 ID 和可恢复 Rhino GUID 与 checkpoint 一致；多出的受管 Box 被移除、被删除的被恢复。新的恢复 operation 有自己的 durable before-checkpoint/Undo 记录；非受管对象逐项不变。
6. `Save managed checkpoint` 不保存整个 3DM，也不覆盖源文件。保存对应 before/after 测试 3DM 作为独立证据。

### 7.5 保存/关闭/重开

保存为本轮测试路径，记录 Document、Session、所有工程 ID/GUID、checkpoint 与 journal。关闭并重新打开同一 `.3dm`，Inspect：Document/工程 ID 保持，Session 必须新建，引用来自真实重开模型。旧 preview/旧 request 不得继续修改。不要“再次初始化”来替代重开身份验证。

保存重开包含普通路径和“请求还在等待时重开”的竞争路径。后者需可控延迟，不可因为前者通过就把 L-07 整行标 PASS。相同 3DM 的文件拷贝可能带同一持久 ID；不能同时加载两个副本来假装两个独立测试文档。破坏性/隔离测试从真正新建空文档开始，各自有新 ID。

## 8. L-01～L-20 完整验收与 F 覆盖

下面的 L 编号、流程和期望来自仓库 [LIVE-ACCEPTANCE.md](../src/RhinoAi.Plugin/LIVE-ACCEPTANCE.md)，F 定义来自 `SPEC.md` §37。**原文件没有直接给出 L→F 对照；本表是按定义建立的覆盖索引，不修改原规范。** 同一个 F 有多个 L 和附加断言，不能由任意一行通过就整体通过。

| L | 必须执行的流程与观察 | 关联 F | 能力/证据要求 |
|---|---|---|---|
| L-01 | Windows 目标版本加载真实插件，打开 RhinoAiPanel 与 RhinoAiFloat，两种 Eto UI/依赖正常 | F-02～F-11 的运行前提；F-01 仅编译 | Rhino SystemInfo、加载路径/二进制哈希、两界面截图。加载不等于编译证据 |
| L-02 | Inspect / Preview / Cancel 前后对照对象表、属性、Undo；未初始化时不能隐式写 ID；已初始化 Preview 只显示 conduit | F-02、F-03 | 第 7.1/7.2；读取和 preview 的独立前后证据，选择检查另见 7.3 |
| L-03 | Box 创建后平移，确切 origin/尺寸/位移；count、GUID、工程 ID、provenance 正确，提交拥有单个 Undo | F-02、F-04 | 第 7.2/7.3；测量结果、request/outcome、before-image |
| L-04 | 对同一 preview 双击提交，并跨停靠/浮窗竞争点击；同 operation 只有一次模型修改和 durable outcome | F-04、F-08、F-09 | 保留同一 operation ID 证据；单按钮被禁用不是跨 UI 并发证明 |
| L-05 | preview 后分别 move/delete/copy 目标、更改 units/tolerance、layer/material/linetype/group；旧预览失效、stale commit 在变更前拒绝 | F-03、F-08、F-11 | 每种变更独立子项；当前文档/会话/版本快照与拒绝结果。复制等可能隔离，使用独立测试文件 |
| L-06 | 原生 Undo 后 Redo，实际几何/ID 跟随 Rhino，revision 对齐、预览失效、不自动重放 | F-05、F-11 | geometry/ID/revision 前中后、Undo/Redo 观察与日志 |
| L-07 | 保存关闭重开；另测 Host 请求挂起时重开 | F-06、F-08 | 同持久 ID、新 session、旧请求取消/清理且不修改新会话；挂起分支需受控时序 |
| L-08 | 对 managed Box 做 Rhino 原生 Copy，保留重复 engineering ID | F-08、F-11 | 应阻止后续 planning，不静默重命名、合并或折叠对象；捕获 QA/rejection |
| L-09 | 独立文档分别测试 managed Box 参与 Split / Join / Boolean / Trim，然后保存重开 | F-08、F-11 | 确认实际拓扑有变化；unsupported lineage/invalid topology 阻止，`lineage-block.txt` 隔离持久。没有发生实际修改的命令不算该子项通过 |
| L-10 | 干净 checkpoint 后 add/move/delete，再 restore；保留非受管对象 | F-07、F-04 | 第 7.4；全部受管几何/属性/ID 对照，非受管指纹/测量不变，恢复前 durable checkpoint |
| L-11 | checkpoint 引用的 layer/material 表身份或属性改变、引用被删除后 restore | F-07、F-08 | 应在模型变更前拒绝不支持的表重建；每类改变单独测试。不能只是对象换层而未影响 checkpoint 原引用 |
| L-12 | Undo disabled 或外层 Undo record 已存在，确实触发 BeginUndoRecord 返回 0 | F-10 | 变更前拒绝，不关闭他人 record。需真实 record 状态观测/受控调试；不能随意改全局 Undo 设置后不还原 |
| L-13 | 延迟 Host Applying ACK 时取消；另将 UI apply 排队后、真正变更前取消 | F-03、F-08、F-10 | geometry 零变更、durable Cancelled 和 `Cancelled before document mutation.`；需可控 ACK/调度，不以快速点取消代替 |
| L-14 | 同步 apply 已开始后请求取消 | F-10 | apply/QA/必要 compensation 与 owned record closure 安全结束，无半程取消；GUI 被同步占用时需调试器/受控 token 时序 |
| L-15 | Add/Replace 之后、属性改变之后、QA 期间分别注入故障 | F-10 | 调试器或经审查专用 instrumented build；同 owned record 内 before-image 补偿、精确核验；不能确认则 FailedRecovery |
| L-16 | Applying 前 journal 写入失败；另在模型 apply 后持久结果写入失败 | F-10 | 前者不改模型，后者隔离不确定状态；需安全受控 I/O 故障，不改系统/用户目录 ACL、不制造全盘磁盘故障 |
| L-17 | 本地 commit 后杀自己的测试 Host/丢 completion ACK；重新配对并恢复 ACK；再验证 native Undo 后也不重放 | F-09、F-05、F-10 | local durable Committed/outcome、Host 状态、几何计数及 ID；当前 UI 无普通 reconnect，需受控方案；另完成同 ID 改 payload 拒绝断言 |
| L-18 | 本地 Applying 已 durable、terminal journal 尚未写入的精确窗口中使专用 Rhino 进程崩溃 | F-10、F-06 | 精确断点/时间线与用户许可；重启 Applying/FailedRecovery 隔离、不重放/假成功。任意时刻强杀不足以通过 |
| L-19 | 延迟 prepare/commit 时关闭浮窗，另关闭当前测试文档 | F-08、F-06、F-10 | 分别验证取消、延期 store/gate disposal、无 disposed-session 回调；关闭浮窗不等于关闭文档，必须各自实测 |
| L-20 | preview 显示期间添加不相关原生对象，然后尝试旧 commit | F-03、F-08、F-11 | 旧 preview 失效，拒绝旧 commit；无无关 Undo、无非受管替换；记录非受管对象完整性 |

### F-01～F-12 的收口标准

- **F-01**：本轮使用真实官方 RhinoCommon/Eto 引用，locked restore、Host/plugin 编译与 win-x64 publish 成功；记录 SDK、lock 与产物哈希。L-01 加载成功不能替代编译证据。
- **F-12**：本轮 Core、真实 HTTP 进程、门禁/证据工具回归实际执行并通过；测试日志、用例数和退出码齐全。fake-adapter/HTTP 通过不等于 live Rhino 通过。

- **F-02**：live 文档 units/tolerance/identity snapshot/目标选择准确，读取无模型变更。不能把 Inspect 的文字摘要当成所有快照字段都已验证。
- **F-03**：detached Preview、Reject/Cancel、真正变更前的取消都无模型变更，包含 L-13 的时序分支。
- **F-04**：精确期望几何/属性/身份，单个 owned Undo，重复点击无第二次修改。
- **F-05**：native Undo/Redo 与实际模型/身份/revision/preview 一致，没有自动重放。
- **F-06**：保存重开保留 ID/历史引用而产生新 session；旧请求及关闭中的 continuation 不再修改。
- **F-07**：受管范围 Restore 的显示、覆盖确认、before-checkpoint、结果和非受管保留均实测；不支持表变更必须拒绝。
- **F-08**：并发、stale revision、切换/关闭文档、目标被改/删除和重复工程 ID 均 fail closed。表中 L-05/L-07/L-19 之外，明确做“在 A preview 后切到 B 文档再尝试提交”的独立子项：两个文档均不能被错误修改。
- **F-09**：丢 ACK 的同 operation 不二次修改；**相同 operation ID 但改变 payload 必须拒绝**。普通 UI 每次 prepare 生成新 ID，不能证明后者；它需要经审查的协议/调试手段，同时观察真实 Rhino，无该能力就 BLOCKED。既有 HTTP 测试仅辅助 F-12。
- **F-10**：真实 BeginUndoRecord=0、部分修改、disk failure、crash during apply 与恢复状态均有证据，不能用“代码有保护”代替。尤其 L-15/L-16/L-18 不完整时该 F 必定未通过。
- **F-11**：manual copy/replace/delete 与 Undo/Redo 身份对齐；split/join 等不支持 lineage 被阻止。必须记录真实 replace/delete 情况，不把 move 的单一演示当全覆盖。

### 8.1 故障测试的安全方案与停点

候选 UI 没有故障注入入口，仓库也没有可直接完成所有真实 Rhino 故障的专用脚本。不要编造命令。普通 agent 无调试权限/工具时：L-15、L-16、L-18 必须 BLOCKED；L-12/13/14/17/19 的精确时序分支通常也 BLOCKED。这会阻塞 F-10，并可能阻塞 F-03/F-06/F-08/F-09；不要只报告“剩三个非关键测试”。

用户批准受控调试后，先提交简短计划：专用进程/新文档、断点或注入位置、预期状态、备份、证据、恢复/退出方式。只使用来源可信且已获准的调试器；专用 instrumented build 会产生不同二进制，必须单独记录源码差异/哈希，不能冒认未注入的候选二进制通过。

源码可用于设计断点的真实位置（这里只定位，不给未经验证的注入脚本）：

- `RhinoDocumentAdapter.Apply`：`Objects.Add` / `Objects.Replace` / `ModifyAttributes` 后与 post-QA；`InOwnedRecord` 的补偿、owned record 验证/closure。
- `ExecutionCoordinator.CommitAsync`：`store.Put(Applying)`、等待 `beforeApply` 的 Host ACK、进入同步 mutation、`store.Put(Committed)` 前后。
- `JsonOperationStore.Put` / `HostJournal`：分别验证 executor 与 Host 的 durable-write 失败；故障只能作用于本轮隔离存储/受控 I/O，不能对用户主目录改 ACL。
- `RhinoUiDispatcher.InvokeAsync` 与 `DocumentSession.CloseWhenIdleAsync`：queued apply/cancel/close 的顺序。
- `AssistantPanel.RecoverAcknowledgement` / `AgentHostClient`：重新配对方案与同 hash durable outcome，仅恢复 ACK，不重新执行几何。

任何 fault 导致 `Applying`、`FailedRecovery`、`recovery-required`、`lineage-block` 或不确定结果：立刻停止该文档的 agent 写入；保留文件与日志，记录实际几何，交给授权人员人工核对。不得循环 Retry Commit、自动 Restore、删除 journal/lock/marker、清空 LocalAppData 或重初始化以“让测试继续”。若需测试其他独立用例，使用真正新建的空测试文档和经确认的安全隔离环境；原失败文档和证据不动。

## 9. 保存持久化证据与身份

真实位置：

```text
%LOCALAPPDATA%\RhinoAi\executor\<persistent-document-id>\operations\
%LOCALAPPDATA%\RhinoAi\executor\<persistent-document-id>\checkpoints\
%LOCALAPPDATA%\RhinoAi\executor\<persistent-document-id>\lineage-block.txt  (若有)
%LOCALAPPDATA%\RhinoAi\host\journal-v1.json  (插件 Start local host 路径)
```

手动启动 Host 未显式设置目录时默认可能是 `RhinoAi\HostJournal`，不要把它与插件固定 `host` 目录混淆。executor 每 operation 一个 JSON，Host 是替换式单文件 journal；二者不是同一个存储。

每条用例记录实际 ID，复制该测试文档对应的 operation/checkpoint 和 Host 状态快照到 `$Evidence`。只在无写入的稳定时点复制，记录时间；如需关闭测试实例释放锁先保存原始状态和观测。不要读取/合并不相关项目的日志。共享 Host journal 含其他文档历史时，先保留受限原件，仅对用户授权范围导出必要记录，不能外传整库。

收尾时对模型、截图、cases、journal/checkpoint、版本/日志等证据生成独立清单；清单不要包含它自身：

```powershell
$EvidencePrefix = [IO.Path]::GetFullPath($Evidence).TrimEnd('\') + '\'
$EvidenceManifest = Join-Path $Evidence 'evidence-sha256.csv'
Get-ChildItem -LiteralPath $Evidence -File -Recurse |
  Where-Object { $_.FullName -ne $EvidenceManifest } |
  ForEach-Object {
    [PSCustomObject]@{
      path = $_.FullName.Substring($EvidencePrefix.Length).Replace('\','/')
      sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      bytes = $_.Length
    }
  } | Export-Csv -LiteralPath $EvidenceManifest -NoTypeInformation -Encoding utf8
```

若之后修改报告或重新运行门禁，最后重新生成清单。原始截图/日志内可能有用户名、绝对路径或模型细节，分享前检查；nonce/密码/token 绝不能进入报告。

## 10. 本轮 acceptance 与 fail-closed 门禁

### 10.1 文件职责与初始状态

`workbuddy-build.ps1` 成功后生成：

| 本轮相对 RunRoot 路径 | 用途 |
|---|---|
| `source-manifest.json` | 本轮源码逐文件 SHA-256 与规范化聚合摘要 |
| `candidate/SHA256.json` | 本轮 Host/plugin 的文件清单、哈希及绑定的源码摘要 |
| `commands.json`、`logs/` | 各构建/测试命令、真实退出码和原始日志 |
| `environment.json`、`build-result.json` | 本轮工具/系统信息，以及构建退出码和初始 gate 退出码 |
| `host-integration/results.json` | 本轮 HTTP 进程测试结果 |
| `acceptance.local.json` | 本轮 F-01～F-12 和 live 环境；不会覆盖历史报告 |
| `live-cases.json` | 本轮 L-01～L-20 的逐行状态、原因和证据引用 |
| `evidence/` | 按第 4/9 节人工收集的 live 证据、模型和报告 |

构建流程先将源码与仓库的 `evidence/repository-workflow/source-manifest.json` 比较，然后生成本轮清单。**不要把旧 `evidence/source-manifest.json` 当成本轮清单，也不要修改已提交清单来让校验通过。** 本轮 source digest 不写死在本文，以脚本校验后的实际值为准。

只有本轮对应命令与日志均真实成功，F-01/F-12 才能由构建脚本记录 PASS；F-02～F-11 和所有 L 行初始为 NOT_RUN。生成文件不代表实际执行 Rhino，脚本不会自动给 live 行盖章。

### 10.2 逐项录入真实 live 结果

保留原始日志，只编辑本轮 `acceptance.local.json` 与 `live-cases.json`。每轮复核前留一个带 UTC 时间的新副本；不要重跑初始化覆盖已录入 live 结果，也不修改仓库历史 `evidence/acceptance.json`。

- 保持 `schema_version`、`candidate`、本轮 `source_digest`、source commit 和自动化事实不变。
- `production_status` 必须始终为 `REVIEW`。当前 `stage1_release` 为 `BLOCKED`；全部要求满足且 gate 返回 0 后才可写技术 `PASS`，该字段本身不会让 gate 通过。
- `checks` 保留 F-01～F-12；`live-cases.json` 保留 L-01～L-20。允许状态仅为 PASS / FAIL / BLOCKED / NOT_RUN。
- 每行 reason 说明实际覆盖、未完成子项与限制。所有 PASS 必须有真实、非空证据文件；L 行 PASS 也要引用证据。
- 证据路径相对**模块根目录**，统一 `/`，例如 `artifacts/workbuddy-runs/<实际RunId>/evidence/cases/L-03.md`。不是相对 RunRoot，不接受外部路径、URL、`C:\...` 或“见截图”文字代替文件。
- live F 行保持 `execution: "live-windows-rhino"`。只要任一 live F 为 PASS，`live_environment` 必须包含真实 `windows_version`、`rhino_version`、`runtime_version`、`source_digest`、`reviewer`。source digest 必须等于本轮源码清单，runtime 应记录 **Rhino 进程**实际 .NET 8 版本。
- 同时在 `evidence/environment/` 保存原始 SystemInfo、OS/SDK/runtime/Python 信息、来源/commit 记录、授权范围和候选路径/哈希。更新 `verified_at_utc` 为实际复核时间。
- 所有 F-02～F-11 为 PASS 前，L-01～L-20 及其所有必测子项必须完成。F-08 的 A/B 文档切换、F-09 的同 ID 改 payload 等额外断言见第 8 节，不因 L 表看似全绿而遗漏。
- 任一实测回归记 FAIL，完整 gate 仍 BLOCKED。不能用仓库历史 F-01/F-12 PASS 掩盖本轮失败或未执行。

JSON 使用 UTF-8 无 BOM。Windows PowerShell 5.1 的 `Out-File -Encoding utf8` / `Set-Content -Encoding utf8` 会加 BOM，不用于改这些 JSON。可用编辑器明确选择 UTF-8 无 BOM，或 .NET `UTF8Encoding(false)` / Python `Path.write_text(..., encoding="utf-8")` 保存。先保留副本，编辑后验证 JSON 能被解析；不要用文字替换批量把 NOT_RUN 改成 PASS。

### 10.3 原生门禁命令与退出码

使用**同一源码、同一 RunRoot**。验收入口不会重新构建、不会初始化或覆盖已录入结果；会复核仓库源码、本轮清单、候选文件、命令证据和 live-cases，再运行技术 gate，并保留本次新的日志/退出码。

```powershell
& (Join-Path $Source 'scripts\workbuddy-verify.ps1') -SourcePath $Source -RunRoot $RunRoot
$GateExit = $LASTEXITCODE
"本次门禁退出码：$GateExit"
```

若 build 时显式指定了工具路径，verify 的 `-Python` 也使用同一有效路径。每次输出保存在 `$RunRoot/verification/<UTC时间戳-唯一ID>/`，包含独立 `logs/` 和结果文件；以脚本实际打印路径为准，保留原始输出，不覆盖先前的 BLOCKED/FAIL。

- **2**：前置校验完成，技术 gate 返回 BLOCKED，例如 live F 尚未通过、live 环境/证据缺失或生产状态不允许。当前自动化成功而实机未完成时，预期得到 2。
- **1**：包装脚本/前置校验失败。例如源码或候选清单不符、命令日志有缺陷、L 证据不完整、工具不可用等，可能在技术 gate 执行前就停止。保留 `failure.txt` 与日志；同样不得放行。
- **0**：技术门禁通过；仍须审阅 L 子项/额外 F 断言和证据内容，工程生产状态仍为 REVIEW。
- **其他退出码/异常**：记录 stdout/stderr 和实际退出码，作为工具/环境故障处理，不能解释为 PASS。

高级诊断可以直接运行 Python gate，但正常交付使用上面的 verify 包装器，因为它还检查本轮来源、候选、命令与 L 证据：

```powershell
py -3 -X utf8 (Join-Path $Source 'scripts\release_gate.py') `
    (Join-Path $RunRoot 'acceptance.local.json') --source-root $Source
```

有外部 `acceptance.local.json` 路径时显式传 `--source-root`，不依赖文件层级猜测。`test_release_gate.py` 测试的是门禁自身能否阻挡坏报告，不能替代对本轮候选运行 release gate。

## 11. 交回报告

将下列模板另存为 `$Evidence\FINAL-REPORT.md`。每条 L/F 都单列，不能只写“其余通过”。原始证据留在约定位置；分享前检查用户名、绝对路径、其他模型记录及秘密，按授权范围交给用户。

```text
Rhino AI Stage 1 本机构建与验收报告
时间范围（UTC）：
操作者 / 复核者：
结论：本地构建 PASS/FAIL/BLOCKED；安装可用/受阻/NOT_RUN；基础冒烟状态；完整技术验收状态
生产状态：REVIEW

来源方式：Git clone / GitHub source archive
仓库 URL / 实际完整 commit / 工作树状态：
归档 commit 核实方法、ZIP SHA-256（如适用）：
仓库源码清单复核、本轮 source digest、本轮 RunRoot：
实际 plugin/host 路径及 candidate/SHA256.json：
Windows 完整版本/架构：
Rhino 完整 build / Rhino 进程 .NET runtime：
系统 .NETCore.App / AspNetCore.App、实际 SDK、Python：

已获授权范围、测试实例、备份、原配置：
Document ID / Session ID / 测试模型路径：
Host endpoint（无 nonce）、所属 PID、journal 位置：

L-01～L-20：逐条列状态、所有子项、证据、剩余阻塞/原因
F-01～F-12：逐条列状态、对应 L/额外断言、证据、原因
历史自动化：仅背景，不作为本轮 Windows 执行结论
本轮自动化：实际用例数、日志、退出码；未执行则 NOT_RUN
门禁：原始命令、日志文件、退出码；源码/候选校验结果

故障/偏差：症状、operation ID、预期/实际、隔离状态、证据
安全退出：测试模型保存、所属 Host 退出、插件注册/保留情况、原设置恢复情况
需要用户决定：具体缺权限、工具、修复或后续调试计划
交付路径：报告、acceptance.local.json、live-cases.json、版本/来源与 hash 清单、models/screenshots/journals/checkpoints
任何超出原批准范围的情况：如实列出
```

遇到缺少调试器等能力时，交回已完成结果和确切阻塞即可。不需要让普通 GUI 工作停在 L-15；但完整 gate 必须保持 BLOCKED，不能报告“所有关键测试已通过”。技术 gate 通过也不授权施工、加工、下料、生产导出或发布。

## 12. 停止、禁用与回退

- 正常结束：确认没有 Applying/挂起请求，保存测试模型和证据，取消仍处 Prepared 的普通 preview，再关闭本轮专用 Rhino。插件 shutdown 会清理其启动的自有 Host；按记录 PID 核对，不能强杀其他同名实例。
- 用户要保留候选：保留完整 candidate 目录和来源/验收记录。插件管理器直接加载 `.rhp` 会记录当前位置，不能测试结束后移动/删除目录而以为 Rhino 已复制安装。说明 REVIEW 和未完成项。
- 用户要停止使用：按当前 Rhino 插件管理器支持的选项禁用本轮插件，记录并按提示重启。直接通过 PlugInManager 安装的 RHP 没有自动卸载流程；[McNeel 官方说明](https://www.rhino3d.com/en/docs/guides/scripts-plugins/how-to-use/)中的手动移除涉及注册信息。不要编造卸载按钮、猜注册表键或直接删注册表。完整移除另行确认具体操作，并交由获准人员按实际版本流程处理。
- 只有确认没有进程加载且用户允许后，才删除本轮候选副本。证据单独保留。若获准改过 runtime 等设置，按保存的原值恢复并验证，不改无关配置。
- 故障/崩溃时先保存实际模型副本、operation、before-checkpoint、Host journal 和错误截图。不能通过删 `%LOCALAPPDATA%\RhinoAi`、覆盖模型或清空 quarantine “卸载干净”。
- 没有自动通用解锁或全文件 Revert。正常 checkpoint Restore 只适用于干净、可验证的当前受管快照，不能绕过隔离。

## 13. 复核入口

- [模块 README](../README.md)：实现范围、当前状态与工程结构。
- [SPEC.md §37](../SPEC.md#37-acceptance-matrix)：F-01～F-12 原始定义。
- [Windows/Rhino live runbook](../src/RhinoAi.Plugin/LIVE-ACCEPTANCE.md)：L-01～L-20、SDK/运行边界。
- [Host runbook](host-runbook.md)：认证、durable state、ACK 与故障语义。
- [协议](PROTOCOL.md)：结构化请求和身份/状态约束。
- [UI 源码](../src/RhinoAi.Plugin/AssistantPanel.cs)、[插件入口](../src/RhinoAi.Plugin/HarnessPlugIn.cs)、[Host client](../src/RhinoAi.Plugin/AgentHostClient.cs)：按钮/命令、运行限制和生命周期。
- [原生 build](../scripts/workbuddy-build.ps1)、[原生 verify](../scripts/workbuddy-verify.ps1)、[本轮证据工具](../scripts/workbuddy_evidence.py)、[技术门禁](../scripts/release_gate.py)：实际执行入口。
- [仓库工作流证据说明](../evidence/repository-workflow/README.md)：新工作流的源码清单与已执行验证；没有 Windows/Rhino 实机证明时不得推断 live 通过。

所有相对链接都在该次取得的仓库源码内，不需要另取聊天附件。与源文件不符时停止相关步骤，记录准确差异；不要临时虚构按钮、工具或成功结果。
