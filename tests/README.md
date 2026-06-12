# VoiceCanvas 测试目录

本目录用于沉淀可运行测试。每个核心模块完成后，都应补充对应测试和运行方式。

## 测试分层

- `domain/`：领域模型、命令、历史、增量 Patch 和用户长期记忆的纯逻辑测试。
- `application/`：CommandValidator、CommandExecutor、runOrchestratorLoop、Session、EventBus、ToolRunner、Memory 服务测试。
- `ai/`：Mock LLM、AIAction Schema、Prompt 输出结构测试。
- `features/`：画布、左侧画布历史区、右侧 AI 交互栏等组件测试。
- `e2e/`：完整语音创作链路、澄清恢复、流式画布更新和导出测试。

项目引入测试框架后，应在本文档补充具体命令，例如 `npm test`、`npm run test:e2e`。
