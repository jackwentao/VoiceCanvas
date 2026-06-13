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

## PR #4：[codex] 调整前后端目录结构

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/4
- PR 状态：Draft
- 分支：`codex/split-frontend-backend-layout`
- 基线分支：`codex/frontend-interaction-prototype`
- 提交：`6958e97 调整前后端目录结构`
- 创建时间：2026-06-12

### 背景

VoiceCanvas 已确认采用前后端分离路线。为了避免前端原型、后端骨架和工程文档长期混在根目录，本 PR 先把已有前端原型迁移到 `frontend/`，为后续 Python 后端独立落地腾出清晰边界。

### 改动

- 将 `package.json`、`package-lock.json`、`scripts/`、`src/prototype/`、`tests/prototype/` 迁移到 `frontend/`。
- 保留前端后续正式化需要的 `frontend/src/app`、`frontend/src/features`、`frontend/tests/features` 和 `frontend/tests/e2e` 占位。
- 清理根目录中原先混合前后端职责的占位目录。
- 更新 `frontend/src/README.md` 和 `frontend/tests/README.md`，说明前端只负责交互、渲染和本地投影。

### 测试

已运行：

```powershell
cd frontend
npm run test:prototype
```

测试结果：`前端交互原型契约测试通过`。

### 风险

- 这是目录迁移 PR，GitHub diff 中会出现较多文件移动。
- 业务逻辑未变更，主要风险是路径引用遗漏；已通过原型契约测试验证。

## PR #5：[codex] 搭建 Python LangGraph 后端骨架

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/5
- PR 状态：Draft
- 分支：`codex/python-langgraph-backend`
- 基线分支：`codex/split-frontend-backend-layout`
- 提交：`845c53a 搭建 Python LangGraph 后端骨架`
- 创建时间：2026-06-12

### 背景

后端技术路线已确定为 Python + uv + FastAPI + LangGraph。需要先建立后端工程骨架，承接后续 AI 编排、可信 Project State、命令校验、命令执行、SSE 事件流、导出和七牛云适配。

### 改动

- 新增 `backend/pyproject.toml` 和 `backend/uv.lock`，使用 uv 管理 Python 依赖。
- 新增 FastAPI 应用入口，包含 `/health` 和 `/api/orchestrations`。
- 新增 LangGraph Mock 编排图，支持普通命令分支和 `WAITING_FOR_USER` 澄清分支。
- 新增 Pydantic 领域模型，覆盖 Project、Scene、CanvasElement、CanvasCommand 等基础结构。
- 新增后端测试，覆盖 API、领域模型和 LangGraph 澄清分支。
- 更新 `.gitignore`，忽略 Python 测试、lint 和类型检查缓存。

### 测试

已运行：

```powershell
cd backend
uv sync --no-editable
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

测试结果：

- pytest：6 passed。
- ruff：All checks passed。
- mypy：Success: no issues found in 12 source files。

说明：pytest 存在 FastAPI TestClient 的上游弃用 warning，不影响当前功能。

### 风险

- 当前 LangGraph 仍是 Mock 编排，只用于验证架构和可恢复分支。
- Windows 中文路径下 editable 安装会导致 `.pth` 路径编码问题，因此后端命令统一使用 `--no-editable`。

## PR #6：[codex] 补充技术选型与依赖声明

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/6
- PR 状态：Draft
- 分支：`codex/document-tech-selection`
- 基线分支：`codex/python-langgraph-backend`
- 提交：见 PR commits，包含技术选型文档同步与 PR 记录更新
- 创建时间：2026-06-12

### 背景

在前端目录迁移和 Python LangGraph 后端骨架落地后，需要同步更新项目文档，避免 README、架构文档和接口文档继续保留旧的 Node/Express 后端表述。

### 改动

- 新增 `docs/技术选型与依赖声明.md`，记录前后端技术栈、依赖边界、运行命令和测试手段。
- 更新 README，补充 `frontend/`、`backend/` 双目录结构、前后端运行方式和测试方式。
- 更新技术架构文档，明确 Python 后端使用 LangGraph 承载可恢复 AI 编排。
- 更新接口与数据模型文档，将实现落点调整为 Python/Pydantic/FastAPI。
- 更新前端交互原型文档和产品决策记录中的路径、模型落地方式和后端职责表述。

### 测试

已运行：

```powershell
cd frontend
npm run test:prototype
```

```powershell
cd backend
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

测试结果：

- 前端交互原型契约测试通过。
- 后端 pytest：6 passed。
- ruff：All checks passed。
- mypy：Success: no issues found in 12 source files。

说明：pytest 存在 FastAPI TestClient 的上游弃用 warning，不影响当前功能。

### 风险

- 本 PR 主要是文档同步，不新增运行时代码。
- 后续如果真实 LLM、ASR 或七牛云 SDK 接入，需要继续同步依赖声明和适配器测试。

## PR #9：[codex] 补充比赛冲刺计划

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/9
- PR 状态：Merged
- 分支：`codex/competition-sprint-plan`
- 基线分支：`main`
- 提交：`bf05b59 补充比赛冲刺计划`
- 创建时间：2026-06-12
- 合并时间：2026-06-12

### 标题

补充比赛冲刺计划与 Demo 指令能力验收文档。

### 功能描述

本 PR 为 VoiceCanvas 增加比赛冲刺与 Demo 验收说明，帮助后续开发、测试和录屏统一目标。

使用方式：

- 通过 README 文档索引进入 `docs/比赛冲刺行动计划.md`，查看 MVP 闭环、优先级、行动顺序和提交验收标准。
- 通过 README 文档索引进入 `docs/Demo脚本与指令能力验收.md`，查看 3 到 5 分钟 Demo 主线、语音指令能力清单、验收语料和测试建议。
- 后续实现 P0 模块、录制 Demo、补测试和准备比赛提交材料时，以这两份文档作为范围约束和验收依据。

### 实现思路

本次变更是文档型 PR，不新增运行时代码。

核心思路：

- 将比赛提交前的工作拆成 P0、P1、P2，优先保证“语音输入 -> AI/Mock 编排 -> 结构化命令 -> 校验执行 -> Project State -> Canvas Patch -> 前端更新 -> 撤销/导出”的稳定闭环。
- 将 Demo 路径固化为可演示脚本，避免后续开发无限扩展语料范围。
- 将语音指令能力拆成创建分镜、镜头管理、添加元素、修改元素、连接线、澄清、撤销、导出、未知元素降级和用户偏好记忆等验收项。
- 更新 README 文档入口，让新文档可以从项目首页直接访问。

### 测试方式

已运行前端原型契约测试：

```powershell
cd frontend
npm run test:prototype
```

结果：前端交互原型契约测试通过。

已运行后端测试、lint 和类型检查：

```powershell
cd backend
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

测试结果：

- pytest：6 passed，1 个 FastAPI TestClient 上游弃用 warning。
- ruff：All checks passed。
- mypy：Success: no issues found in 12 source files。

手动验证方式：

- 打开 README，确认文档索引包含 `Demo 脚本与指令能力验收` 和 `比赛冲刺行动计划`。
- 点击两份文档链接，确认能正确跳转并阅读对应内容。
- 对照 `docs/Demo脚本与指令能力验收.md` 中的主线脚本，检查后续实现是否覆盖创建、修改、澄清、撤销和导出。

## PR #10：[codex] 实现后端命令执行闭环

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/10
- PR 状态：Draft
- 分支：`codex/backend-command-pipeline`
- 基线分支：`main`
- 提交：本 PR 当前提交 `实现后端命令执行闭环`
- 创建时间：2026-06-12

### 标题

实现后端命令校验、执行、历史记录、撤销重做和画布 Patch 闭环。

### 功能描述

本 PR 为 VoiceCanvas 后端补齐应用层确定性写操作链路，使后续 AI Orchestrator 或工具调用只要产出合法 `CanvasCommand`，就能通过统一流程修改可信 Project State。

使用方式：

- 调用 `CommandValidator.validate()` 校验 AI 或工具生成的一组画布命令。
- 调用 `CommandExecutor.execute()` 或 `execute_batch()` 执行合法命令，并获得更新后的 `Project`、`CanvasPatch` 和 `HistoryEntry`。
- 调用 `HistoryManager.record()` 记录成功操作，使用 `undo()` 和 `redo()` 基于历史逆命令回退或恢复画布状态。
- 当用户删除最后一个 `Scene` 时，系统不会删除项目最后页面，而是解释为清空当前页面，保留 `activeSceneId` 并生成 `SCENE_CLEARED` Patch。

### 实现思路

本次实现保持后端分层解耦，不接入 `/api/orchestrations` 真实执行流程。

核心思路：

- 在 `domain/` 层新增 `CanvasPatch`、`HistoryEntry` 和 `UndoRedoState`，让 Project State、画布增量和操作历史有统一数据结构。
- 继续保留 `CanvasCommand.payload` 的通用字典设计，由 `CommandValidator` 按命令类型校验必填字段、目标 Scene/Element 和坐标尺寸，降低比赛期间模型迁移风险。
- 在 `CommandExecutor` 中集中处理 `CREATE_SCENE`、`UPDATE_SCENE`、`DELETE_SCENE`、`SWITCH_SCENE`、`ADD_ELEMENT`、`UPDATE_ELEMENT`、`DELETE_ELEMENT` 和基础 `ARRANGE_LAYOUT`。
- 每条成功命令都生成可追溯 `commandId` 的 Patch 和可执行的 `inverseCommand`，供历史撤销重做复用。
- `HistoryManager` 维护 undo/redo 栈；普通新命令会清空 redo 栈，undo/redo 本身不追加新的普通历史记录。

### 测试方式

已运行后端测试、lint 和类型检查：

```powershell
cd backend
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

测试结果：

- pytest：21 passed，1 个 FastAPI TestClient 上游弃用 warning。
- ruff：All checks passed。
- mypy：Success: no issues found in 17 source files。

新增测试覆盖：

- `test_command_validator.py`：校验核心命令、缺字段、目标不存在、非法尺寸和删除最后一个 Scene 的清空语义。
- `test_command_executor.py`：校验创建镜头、添加/修改/删除元素、删除 active Scene、清空最后页面和居中布局。
- `test_history_manager.py`：校验添加、修改、删除、清空页面的 undo/redo，以及新命令清空 redo 栈。

## PR #11（GitHub #12）：[codex] 接入真实后端编排 API

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/12
- PR 状态：Draft
- 分支：`codex/real-backend-orchestration-api`
- 基线分支：`main`
- 提交：本 PR 当前提交 `接入真实后端编排 API`
- 创建时间：2026-06-12
- 编号说明：项目记录顺序上这是 PR #11；GitHub 上误开的旧 #11 已关闭且编号不可复用，因此平台实际编号为 #12。

### 标题

接入同步版真实后端编排 API，返回 Project、Patch、History、事件和总结。

### 功能描述

本 PR 将 `/api/orchestrations` 从 Mock LangGraph 响应升级为真实后端业务闭环。用户或前端提交演示语料后，后端会读取或创建 Project，生成结构化命令，经过命令校验和执行器更新 Project State，并同步返回本轮 CanvasPatch、HistoryEntry、运行事件和 Turn Summary。

使用方式：

- 启动后端服务后，调用 `POST /api/orchestrations`。
- 请求体包含 `projectId` 和 `userInput`。
- 响应中读取 `project` 更新当前画布投影，读取 `patches` 做局部刷新，读取 `history` 展示操作历史，读取 `events` 和 `summary` 展示右侧 AI 交互栏状态。
- 当前自然语言理解由 `DemoCommandPlanner` 覆盖比赛演示语料，包括创建三镜头分镜、切换第二镜头、添加标题/商品/标签/箭头、修改标题、放大商品、删除标题、删除最后镜头、撤销和重做。

### 实现思路

本次变更保持“小 PR 单一功能”，只接入真实后端业务 API，不接真实 LLM、ASR、SSE、导出和七牛云存储。

核心思路：

- 新增 `InMemoryProjectRepository`，为 Demo 阶段提供可连续调用的项目状态存储。
- 新增 `DemoCommandPlanner`，把有限比赛演示语料转换为合法 `CanvasCommand`，后续可由真实 LLM Adapter 替换。
- 新增 `OrchestrationService`，串联 ProjectRepository、DemoCommandPlanner、CommandValidator、CommandExecutor 和 HistoryManager。
- 扩展 `/api/orchestrations` 响应，保留 `nextAction` 兼容字段，同时返回真实 `project`、`patches`、`history`、`events` 和 `summary`。
- 同步 README、后端 README、接口文档、前端绑定文档和比赛冲刺计划，确保 main 分支状态说明与运行效果一致。

### 测试方式

已运行后端测试、lint 和类型检查：

```powershell
cd backend
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

已运行前端原型契约测试：

```powershell
cd frontend
npm run test:prototype
```

测试结果：

- pytest：36 passed，1 个 FastAPI TestClient 上游弃用 warning。
- ruff：All checks passed。
- mypy：Success: no issues found in 20 source files。
- 前端交互原型契约测试通过。

新增测试覆盖：

- `test_project_repository.py`：验证内存 Project Repository 创建、保存、读取和项目隔离。
- `test_demo_command_planner.py`：验证 Demo 语料能生成创建分镜、切换镜头、修改标题和删除镜头命令。
- `test_orchestration_service.py`：验证真实编排闭环、Project 保存、Patch 返回、History 记录、撤销和重做。
- `test_api.py`：验证 `/api/orchestrations` 返回真实 Project、Patch、History、Events，并能在同一个 projectId 上连续修改状态。

## PR #18：[codex] 修复语义对象尺寸更新同步

- PR 链接：https://github.com/jackwentao/VoiceCanvas/pull/18
- PR 状态：Open
- 分支：`codex/sync-semantic-element-size-patches`
- 基线分支：`main`
- 提交：本 PR 当前提交 `修复语义对象尺寸更新同步`
- 创建时间：2026-06-13

### 标题

修复人物、猫、桌子等语义对象的尺寸更新同步。

### 功能描述

本 PR 修复后定义语义对象无法放大或缩小的问题。用户通过“放大猫”“缩小人物”“把桌子变大”等指令触发 `UPDATE_ELEMENT` 后，无论 Planner 输出旧字段 `width/height`，还是输出结构化字段 `transform.width/height`，后端 Project State 和前端本地降级演示都会保持两套字段同步，画布渲染器可以立即读到最新尺寸。

使用方式：

- 后端编排或 LLM Planner 继续生成合法 `UPDATE_ELEMENT` 命令。
- `patch` 可以使用旧字段 `width/height`，也可以使用 `transform: { width, height }`。
- 前端原型渲染时继续优先读取 `transform`，旧字段作为兼容输入。

### 实现思路

本次变更保持“小 PR 单一功能”，只修复元素尺寸补丁同步，不新增第三方依赖。

核心实现：

- 后端新增 `application/element_patch.py`，集中处理元素补丁浅合并，并同步 `transform` 与旧字段镜像。
- `CommandValidator` 和 `CommandExecutor` 共用同一个补丁合并器，避免校验通过但执行结果不同步。
- 前端新增 `frontend/src/prototype/element-patch.js`，用于本地降级演示命令链路，保证后端不可用时语义插画对象也能缩放。
- README 和对象模型设计文档同步说明该原创补丁合并能力；本次未新增第三方库、框架、SDK 或外部服务。

### 测试方式

已运行后端命令执行回归测试：

```powershell
cd backend
uv run --no-editable pytest tests/test_command_executor.py
```

已运行后端全量测试：

```powershell
cd backend
uv run --no-editable pytest
```

已运行本次变更涉及文件的 lint：

```powershell
cd backend
uv run --no-editable ruff check src/voicecanvas/application/element_patch.py src/voicecanvas/application/command_executor.py src/voicecanvas/application/command_validator.py tests/test_command_executor.py
```

已运行前端原型契约测试：

```powershell
cd frontend
npm run test:prototype
```

测试结果：

- `tests/test_command_executor.py`：9 passed。
- 后端全量 pytest：74 passed，1 个 FastAPI TestClient 上游弃用 warning。
- 本次变更涉及文件 ruff：All checks passed。
- 前端交互原型契约测试通过。
- 说明：仓库全量 `ruff check .` 和 `mypy src` 当前仍会暴露既有 `llm_command_planner.py`、`render_catalog.py`、`domain/project.py` 等静态检查问题；本 PR 不扩大范围修复这些历史问题，避免破坏“小 PR 单一功能”。

新增测试覆盖：

- `test_executor_keeps_transform_and_legacy_size_in_sync`：验证 `generated_asset` 使用旧字段 `width/height` 和结构化 `transform.width/height` 更新时，两个字段镜像保持一致。
- `testElementPatchMirrorSync`：验证前端本地补丁合并器在旧字段和结构化字段两种输入下都同步尺寸和图层镜像。
