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
