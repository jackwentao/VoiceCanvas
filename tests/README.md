# VoiceCanvas 测试目录

本目录用于沉淀可运行测试。每个核心模块完成后，都应补充对应测试和运行方式。

## 测试分层

- `domain/`：领域模型、命令、历史、增量 Patch 和用户长期记忆的纯逻辑测试。
- `application/`：CommandValidator、CommandExecutor、runOrchestratorLoop、Session、EventBus、ToolRunner、Memory 服务测试。
- `ai/`：Mock LLM、AIAction Schema、Prompt 输出结构测试。
- `features/`：画布、左侧画布历史区、右侧 AI 交互栏等组件测试。
- `e2e/`：完整语音创作链路、澄清恢复、流式画布更新和导出测试。

项目引入测试框架后，应在本文档补充具体命令，例如 `npm test`、`npm run test:e2e`。

## 当前可运行测试

前端交互原型契约测试：

```powershell
npm run test:prototype
```

或直接运行：

```powershell
node tests/prototype/prototype-contract.test.mjs
```

该测试验证 `src/prototype/mock-data.js` 中的 API 契约、UI 绑定、指令链路和初始 Project 数据模型，确保前端原型与后端接口设计保持强绑定。
