# VoiceCanvas 源码目录

本目录按当前技术架构文档拆分模块，核心原则是领域模型、应用服务、AI 编排、适配器和界面特性解耦。

## 目录说明

- `app/`：应用入口、全局 Provider 和装配逻辑。
- `features/`：面向页面功能的 UI 模块，包括画布、右侧 AI 交互栏、左侧画布历史区、分镜和导出面板。
- `ai/`：AI Orchestrator、Prompt 和 Schema。
- `application/`：命令执行、命令校验、可恢复会话、事件总线、工具运行和用户长期记忆服务。
- `domain/`：纯领域模型，包括项目、镜头、元素、命令、历史、增量 Patch 和用户记忆。
- `adapters/`：LLM、ASR、存储、导出等外部能力适配器。
- `infrastructure/`：七牛云、日志、配置等基础设施封装。

实现时应优先补齐 TypeScript 类型、Zod Schema、CommandValidator、CommandExecutor 和 runOrchestratorLoop。
