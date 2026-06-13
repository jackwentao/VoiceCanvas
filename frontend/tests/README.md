# VoiceCanvas 测试目录

本目录用于沉淀可运行测试。每个核心模块完成后，都应补充对应测试和运行方式。

## 测试分层

- `domain/`：领域模型、命令、历史、增量 Patch 和用户长期记忆的纯逻辑测试。
- `application/`：CommandValidator、CommandExecutor、runOrchestratorLoop、Session、EventBus、ToolRunner、Memory 服务测试。
- `ai/`：Mock LLM、AIAction Schema、Prompt 输出结构测试。
- `features/`：画布、左侧画布历史区、右侧 AI 交互栏等组件测试。
- `e2e/`：完整语音创作链路、澄清恢复、流式画布更新和导出测试。

项目已声明 Vitest 作为后续前端单元测试工具。正式前端模块落地后，应在本文档补充具体命令，例如 `npm run test:features`、`npm run test:e2e`。

## 当前可运行测试

前端交互原型契约测试：

```powershell
cd frontend
npm run test:prototype
```

或直接运行：

```powershell
cd frontend
node tests/prototype/prototype-contract.test.mjs
```

该测试验证 `frontend/src/prototype/mock-data.js` 中的 API 契约、UI 绑定、指令链路和初始 Project 数据模型，确保前端原型与后端接口设计保持强绑定。

本轮新增的元素补丁测试还会直接校验 `frontend/src/prototype/element-patch.js`：

- 旧字段 `width/height` 更新时，会同步写入 `transform.width/height`。
- 结构化 `transform.width/height` 更新时，会同步写回旧字段，保证本地降级演示中的语义插画对象可以缩放。

本轮新增的后端绑定测试还会检查：

- `frontend/src/prototype/backend-client.js` 是否保留项目状态与编排 API 调用。
- `frontend/src/prototype/state-sync.js` 是否把后端 `project`、`history`、`events` 和 `summary` 统一归并到前端状态。
- `frontend/src/prototype/app.js` 是否在启动时拉取后端状态，并把 AI 指令统一提交到后端编排入口。

## 后续测试工具声明

- 前端纯逻辑和组件测试：使用 `vitest`。
- 后端 API、领域模型和 LangGraph 测试：在 `backend/` 中使用 `pytest`。
- 前端 E2E 测试：等正式前端引入后再添加 `playwright`。

新增模块时，需要同步说明测试文件位置、运行命令、覆盖场景和未覆盖风险。
