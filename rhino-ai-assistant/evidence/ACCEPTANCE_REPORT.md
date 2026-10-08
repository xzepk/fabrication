# Rhino AI Agent Harness：第一阶段实现候选验收报告

验证时间：2026-10-08 02:15 UTC。状态：**REVIEW；第一阶段实机发布门禁 BLOCKED**。

## 已完成

- 基于仓库真实 `rhino-ai-assistant/SPEC.md` v0.1 更新为 v0.2，保留通用 Harness 架构，拆为基础闭环、包覆场景、专家/设计探索、团队平台四阶段。
- 6 个 .NET 项目整体 Release 编译通过：0 警告、0 错误。实际生成 `RhinoAi.Plugin.rhp`，引用官方 RhinoCommon/Eto SDK；没有用伪造 SDK 代替。
- 编译了 Windows x64 的 `RhinoAi.Host.exe`；这是 Linux 上交叉编译的框架依赖候选包，没有在 Windows 中执行。需要 Windows 上另有 .NET 8 ASP.NET Core Runtime。
- 实现受管 Box 创建、平移及受管范围 Checkpoint Restore，配套 Preview、明确接受、持久化操作记录、重放去重、取消、过期上下文检查、失败隔离及实际 Rhino 适配器。

## 验证结果（互不重复的计数）

| 检查 | 结果 | 边界 |
|---|---|---|
| Core 回归 | 37/37 通过 | Fake Adapter，含并发、队列取消、丢 ACK、保存重启、损坏日志及部分失败；不是 Rhino 实机验证 |
| Host HTTP/进程集成 | 52/52 通过 | 实际启动 ASP.NET Host 并请求 HTTP，验证鉴权、严格 JSON、持久化、重启、重复请求、恢复确认、存储故障 |
| Release gate 回归 | 40 条断言通过 | 拒绝缺失/陈旧来源、伪装实机证据和生产状态越权 |
| 整体 Release build | 通过，0 警告/0 错误 | 6 项目 |
| Windows Host 交叉编译 | 通过 | Windows PE x86-64；未执行 Windows 验收 |
| 补丁应用检查 | 通过 | 对照真实上游 SPEC 字节，git apply --check 成功 |
| 既有 cladding-delivery | 56/56 清单校验通过 | 与原有 MANIFEST 一致 |
| 既有 cad-fabrication-engineering-v3 | 35/35 清单校验通过 | 与原有 MANIFEST 一致，包含原始 DWG |

89 个自动化用例（37 Core + 52 HTTP）通过；门禁的 40 条断言单列，不混算为额外集成用例。

## 尚未通过的实机门禁

F-02 至 F-11 均为 NOT_RUN。Windows Rhino 环境和许可证在当前执行环境不可用，未把编译或假适配器测试写成实机通过。

必须在 Windows Rhino 8.20/.NET8 及明确记录的服务版本中验证：

1. 插件加载、浮动和停靠界面、真实文档/单位/容差/选择读取。
2. Preview 和 Reject 不改文档；接受后几何、标识、单个 Undo 记录准确。
3. 原生 Undo/Redo、人工修改、复制冲突、切换/关闭文档、保存/重开后的身份和会话一致性。
4. Checkpoint Restore 精确恢复受管范围，同时保留非受管对象，并说明覆盖后续人工编辑的影响。
5. BeginUndoRecord=0、取消时序、部分修改故障、磁盘写入失败、Rhino/Host 崩溃、丢失确认和重连不重复执行。

逐项操作和 20 条实机用例见 `src/RhinoAi.Plugin/LIVE-ACCEPTANCE.md`。自动门禁当前正确返回 exit 2（BLOCKED）。

## 明确限制

- 本次是第一阶段代码候选，不是完整 Harness、V1 发布或可直接生产下单的包覆系统。
- LLM 自然语言规划、cladding Skill 集成、图纸/BOM/套料、一般历史 Revert/合并仍在后续阶段。
- Checkpoint Restore 仅覆盖明确支持的受管对象。真实部分失败/不确定状态会隔离后续写入，需人工审核恢复；没有自动解除隔离入口。
- 引用官方 `RhinoCommon [8.20.25147.11001-rc]` SDK 包；其运行兼容性必须实机验收。没有捏造不存在的稳定 8.20 NuGet 版本。
- 未推送仓库、未创建 PR、未安装到用户电脑、未修改既有两套 Skill 或原始 DWG。

## 复核来源

- 上游基准：`9561a0b929f9191e66230196d1be1d7453115aff`
- 原始 SPEC Git blob：`114630e189f7d698eb872acab19af59cf13b1254`
- 本候选源码摘要：`f03be27fef5aecc3281c9b17f3108bea6a786b97470747fc25643ad6d07795ae`
- 完整日志和机器可读结果：源码包内 `evidence/`
- 后续授权发布所需补丁：`evidence/source.patch`
