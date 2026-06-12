# VoiceCanvas PR 提交记录

> 本文档用于记录 VoiceCanvas 项目的 PR 提交历史，便于后续回看每次变更的背景、范围、验证方式和遗留风险。

## PR #1：scaffold VoiceCanvas architecture

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/1
- PR 状态：Draft
- 分支：`codex/scaffold-voicecanvas-architecture`
- 提交：`eef85db docs: scaffold VoiceCanvas architecture`
- 创建时间：2026-06-12

### 背景

VoiceCanvas 已经明确采用可恢复 AI 编排器架构，需要把产品决策、技术架构、接口数据模型和工程目录骨架同步沉淀，方便后续按模块实现和测试。

### 改动

- 新增技术架构设计文档，明确可恢复 AI Orchestrator、循环执行模型、Tool Calling、Clarification、CanvasPatch 流式更新、左侧画布历史区、右侧 AI 交互栏和用户长期记忆。
- 新增接口与数据模型设计文档，覆盖 Project、Scene、CanvasElement、CanvasCommand、CanvasPatch、History、AIAction、TaskPlan、OrchestrationSession、UserMemory、Tool、Repository、Exporter、ASR/LLM 等模型和端口。
- 更新产品决策记录、语音指令语料和 README，使文档状态与架构决策保持一致。
- 创建 `src/` 工程目录骨架，按 app、features、ai、application、domain、adapters、infrastructure 分层。
- 创建 `tests/` 测试目录骨架，按 domain、application、ai、features、e2e 分层，并补充测试目录说明。

### 测试

- 已运行 Markdown 相对链接检查：`OK all markdown links`。
- 已通过仓库 pre-commit 校验。
- 已通过仓库 commit-msg 校验。
- 当前变更主要是文档和目录骨架，项目尚未引入 package/test runner，因此暂无可运行单元测试命令。

### 风险

- 目前只完成架构、接口和目录骨架，尚未实现 TypeScript 类型、Zod Schema、CommandExecutor、runOrchestratorLoop 等代码。
- `src/` 和 `tests/` 目录目前使用 `.gitkeep` 保留结构，后续实现模块时需要替换为真实代码和测试。
- 用户长期记忆作为加分项已经设计，但还需要确认 MVP 中实现到本地存储还是只做 Mock 演示。
- 本地环境没有安装 GitHub CLI `gh`，PR 创建使用 GitHub 插件完成。

### 截图或录屏

不涉及前端 UI 实现，暂无截图或录屏。

## PR #2：[codex] 实现 VoiceCanvas 前端交互原型

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/2
- PR 状态：Draft
- 分支：`codex/frontend-interaction-prototype`
- 基线分支：`codex/scaffold-voicecanvas-architecture`
- 提交：`55d2554 实现前端交互原型`
- 创建时间：2026-06-12

### 背景

VoiceCanvas MVP 需要先具备可演示的前端交互原型，用于验证左侧画布历史区、中间结构化画布、右侧 AI 交互栏和项目级设置入口是否符合产品与架构设计。同时，页面交互需要强绑定后端接口模型，方便后续替换为真实 Orchestrator、CommandExecutor、SSE 和导出服务。

### 改动

- 新增 `src/prototype/` 静态前端原型，包含左侧画布历史区、中间结构化画布和右侧 AI 交互栏。
- 新增项目设置菜单，提供新建项目、载入项目、导出 JSON 和导出图片入口。
- 实现语音输入草稿流程：识别完成后进入可编辑文本，用户确认后再发送。
- 支持 `Alt+V` 录音快捷键，松开后生成可编辑转写草稿。
- 将页面改为稳定三栏独立滚动布局，左右区域内容增长不影响中间画布稳定性。
- 新增 `docs/前端交互原型与接口绑定设计.md`，说明页面区域职责、接口绑定、事件流和测试方式。
- 新增 `tests/prototype/prototype-contract.test.mjs`，覆盖 API 契约、UI 绑定、初始项目模型和关键交互入口。
- 新增 `scripts/serve-prototype.mjs` 和 `npm run prototype`，用于稳定运行本地原型。

### 测试

- 已运行原型契约测试：

```powershell
npm run test:prototype
```

- 测试结果：`前端交互原型契约测试通过`。
- 已在浏览器手动验证：
  - 设置菜单默认收起，点击展开，再次点击可收回。
  - `Alt+V` 可以生成可编辑转写草稿，且不会自动执行。
  - 页面移除底部调试面板后保持三栏稳定布局。

### 风险

- 当前仍是静态 Mock 原型，尚未接入真实 ASR、LLM、BFF 或 SSE。
- 语音识别流程为原型模拟，后续需要替换为真实 `SpeechRecognizer`。
- 导出入口已设计，但 PNG、长图导出和七牛云存储还需要后续接入真实 `Exporter` 与 `AssetStorage`。

### 截图或录屏

前端原型可通过以下命令本地启动查看：

```powershell
npm run prototype
```

访问地址：

```text
http://127.0.0.1:4178/index.html
```
