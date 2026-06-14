# VoiceCanvas

VoiceCanvas 是一款面向内容创作者的纯语音创作草图工具，参赛题目为七牛云 XEngineer「AI 语音绘图工具」。

用户不需要使用鼠标、键盘，也不需要掌握 PS、Figma 或复杂 prompt，只需要通过语音就能创建、修改、组织和导出单张场景草图或短视频分镜草稿。

## 项目定位

传统文生图工具擅长生成单张结果图，但不擅长持续、精确、低成本地修改画面。VoiceCanvas 的目标不是替代文生图，而是提供一个更适合创作前期沟通的工作流：

```text
语音表达创意
↓
生成结构化草图或分镜
↓
继续语音添加、修改、删除元素
↓
用箭头、连接线和说明表达画面关系
↓
导出可沟通的创作草稿
```

一句话差异化：

> VoiceCanvas 不是 Voice-to-Image，而是 Voice-to-Editable-Storyboard。

## 目标用户

优先服务短视频内容创作者，包括：

- 带货视频创作者
- 探店视频创作者
- 知识教程类创作者
- 需要快速表达画面想法的策划、运营、编导或产品人员

## MVP 能力

当前 MVP 聚焦证明一件事：

> 用户不使用鼠标和键盘进行核心创作操作，也能在 3 分钟内完成一组可展示、可修改、可导出的创作草稿。

MVP 计划支持：

- 创建自由画布
- 创建多镜头分镜
- 根据主题生成初始内容
- 语音新增、删除、切换镜头
- 语音添加人物、商品、文字、标签、背景、箭头、连接线和未知元素
- 语音修改元素文字、颜色、大小、位置、时长和说明
- 语音调整布局、图层和基础风格
- 撤销、重做、清空
- 导出图片和 JSON 项目数据

## 核心设计

VoiceCanvas 使用结构化画布，而不是把整张画面当成不可编辑图片。

每个画面由元素列表组成：

```ts
{
  id: string;
  name: string;
  type: "shape" | "text" | "template" | "generated_asset" | "connector";
  x: number;
  y: number;
  width: number;
  height: number;
  zIndex: number;
}
```

这样用户可以继续通过语音精确修改：

- “把商品放大一点”
- “把标题移到顶部”
- “删除优惠标签”
- “从奶茶指向低糖标签画一个箭头”
- “把第二镜头说明改短一点”

对于系统暂未内置的元素，MVP 至少生成语义占位元素；如果接入生图能力，则优先按元素级生成，不进行整图重生成。

## 文档

- [产品决策记录](./docs/产品决策记录.md)
- [语音指令语料](./docs/语音指令语料.md)
- [Demo 脚本与指令能力验收](./docs/Demo脚本与指令能力验收.md)
- [技术架构设计](./docs/技术架构设计.md)
- [技术选型与依赖声明](./docs/技术选型与依赖声明.md)
- [接口与数据模型设计](./docs/接口与数据模型设计.md)
- [前端交互原型与接口绑定设计](./docs/前端交互原型与接口绑定设计.md)
- [长期记忆 MVP 决策](./docs/长期记忆MVP决策.md)
- [比赛冲刺行动计划](./docs/比赛冲刺行动计划.md)
- [PR 提交记录](./docs/PR提交记录.md)

## 参赛有效性与协作规则

本项目的 README、PR 描述和依赖声明直接关系到参赛作品有效性，后续开发必须遵守以下规则：

- 新功能和功能修改必须基于 PR 合入。
- 每个 PR 只做一件事，只实现或修改单一功能；大功能拆分为多个独立小 PR 分步提交。
- PR 标题需用一句话说明新增或修改内容。
- PR 描述必须包含功能描述、实现思路和测试方式。
- 每次合并后主分支必须保持可运行，评委在任意时间查看都应能按本 README 复现演示效果。
- 新增第三方库、框架、SDK 或外部服务时，必须同步更新本 README 和 [技术选型与依赖声明](./docs/技术选型与依赖声明.md)，列明依赖名称、用途、使用边界、降级方案和测试方式。

当前第三方依赖概览：

| 位置 | 依赖 | 用途 |
| --- | --- | --- |
| `frontend/package.json` | `express`、`cors`、`zod` | 原型静态服务、本地跨端口调试准备、前端契约或输入校验准备 |
| `frontend/package.json` | `typescript`、`tsx`、`vitest`、`supertest` 及类型包 | 后续正式前端类型、脚本与测试工具 |
| `backend/pyproject.toml` | `fastapi`、`uvicorn[standard]` | 后端 HTTP API 与本地服务运行 |
| `backend/pyproject.toml` | `pydantic` | 领域模型、请求响应和命令校验 |
| `backend/pyproject.toml` | `langgraph`、`langchain-core` | 可恢复 AI 编排与 LLM 适配基础类型 |
| `backend/pyproject.toml` | `httpx`、`python-dotenv` | 外部服务 HTTP 调用与本地环境变量加载 |
| `backend/pyproject.toml` | `minio` | 统一风格带货素材包的 MinIO 私有桶读取；仅在存储适配器层懒加载使用 |
| `backend/pyproject.toml` | `pytest`、`pytest-asyncio`、`respx`、`ruff`、`mypy` | 后端测试、外部 HTTP Mock、lint 与类型检查 |
| Python 标准库 | `sqlite3` | 默认持久化 Project State，不新增第三方依赖 |
| 外部服务 | DeepSeek OpenAI-compatible API | 真实 LLM Planner 的自然语言理解能力；仅通过 `adapters/llm` 接入，可降级到 Demo Planner |
| 浏览器原生 API | Web Speech API（`SpeechRecognition` / `webkitSpeechRecognition`） | 持续语音创作模式的中文语音转写入口；仅在前端适配层使用，可被后续云端 ASR adapter 替换 |
| 浏览器原生 API | SpeechSynthesis | 系统语音反馈播报；仅用于演示交互反馈，不参与后端可信状态判断 |

当前原创功能部分：

- 语音到可编辑分镜草稿的产品工作流设计。
- 结构化画布、镜头、元素、连接线和历史记录的项目数据模型。
- 元素补丁合并与 `transform`/旧尺寸字段镜像同步，保证人物、猫、桌子等语义对象可持续缩放和移动。
- 命令校验、命令执行、历史记录和项目状态更新链路。
- SQLite Project Repository：默认把 Project State 持久化到 `backend/data/voicecanvas.sqlite3`，支持重启后继续读取项目。
- 面向可恢复 AI 编排的应用层接口、演示 Planner、真实 LLM Planner 输出校验与降级链路。
- 面向“左边那个杯子 / 那个标签 / 它”等用户表达的指代消解、候选澄清和恢复上下文设计。
- 并行工具结果聚合后统一回灌 Orchestrator 的应用层缓冲机制。
- Render Catalog 语义渲染能力目录、别名归一化、前端 renderer registry 和不支持对象的生成素材占位降级策略。
- MinIO 素材包代理渲染链路：Render Catalog 保存稳定对象路径，后端校验并代理 `catalog/commerce/` 素材，前端按路径加载图片并在失败时占位降级。
- 前端原型中的画布投影、历史区、AI 交互栏和导出入口设计。
- 可复用导出与载入能力：前端按钮可直接导出当前项目包或当前分镜图片，语音/LLM 路径可通过 `EXPORT_PROJECT` 调用同一导出服务，项目包可再次载入恢复为可编辑 Project State。
- 画布文字元素的自适应排版能力，根据元素边界和中英文混排内容估算字号并避免文本裁剪。
- 持续语音创作会话状态机，包括首次授权后持续监听、最终转写自动提交、系统播报期间停止监听、播报结束提示音恢复收音和“结束创作”退出。
- 高风险清空画布的语音确认闭环，包括 `CLEAR_SCENE` 命令、确认/取消恢复逻辑、撤销历史和噪声不入后端指令系统的前端过滤。
- 用户长期记忆后端 MVP，包括偏好模型、来源证据、本地 JSON 仓储、状态流转、相关性检索和敏感信息过滤。
- 用户长期记忆接入编排主链路：每轮编排会按用户输入检索相关 active 记忆，并以 `userMemoryContext` 注入 Planner；candidate、rejected 和 archived 记忆不会自动影响 AI 决策。

第三方框架只作为服务运行、模型校验、编排基础设施和测试工具使用；VoiceCanvas 的业务规则、画布状态变更、命令语义和演示工作流为本项目原创实现。

## 项目结构

```text
frontend/  前端静态原型与后续正式前端
backend/   Python + FastAPI + LangGraph 可信后端
docs/      产品、架构、接口和工程说明
```

前端负责语音入口、画布投影、历史区、AI 交互栏和导出入口；后端负责 Project 可信状态、AI 编排、命令校验、命令执行、历史记录、事件流、导出和外部服务适配。

## 运行与测试

前端原型：

```powershell
cd frontend
npm run prototype
```

访问：

```text
http://127.0.0.1:4178/index.html
```

前后端联调时，先启动后端服务，再启动前端原型：

```powershell
cd backend
$env:PYTHONPATH="src"
uv run --no-editable uvicorn voicecanvas.api.main:app --reload
```

```powershell
cd frontend
npm run prototype
```

页面启动后会自动请求 `GET /api/projects/project_demo_voicecanvas` 同步后端 Project State；发送语音转写或点击演示指令时，会调用 `POST /api/orchestrations`，并用返回的 `project`、`history`、`events` 和 `summary` 同步画布、左侧历史区和右侧 AI 交互栏。若后端未启动，前端会记录 `BACKEND_REQUEST_FAILED` 事件并降级到本地演示链路，便于比赛现场保底展示。

前端契约测试：

```powershell
cd frontend
npm run test:prototype
```

后端环境与测试：

```powershell
cd backend
uv sync --no-editable
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

项目状态默认持久化到 SQLite：

```powershell
$env:VOICECANVAS_PROJECT_DB_PATH="D:\tmp\voicecanvas.sqlite3"
```

未设置时使用 `backend/data/voicecanvas.sqlite3`。本功能使用 Python 标准库 `sqlite3`，没有新增第三方依赖；长期记忆当前仍保留独立 JSON 仓储，后续会按独立 PR 迁移。

MinIO 素材包配置：

```powershell
cd backend
$env:VOICECANVAS_ASSET_PROVIDER="minio"
$env:VOICECANVAS_MINIO_ENDPOINT="127.0.0.1:9000"
$env:VOICECANVAS_MINIO_BUCKET="voicecanvas-assets"
$env:VOICECANVAS_MINIO_ACCESS_KEY="your-access-key"
$env:VOICECANVAS_MINIO_SECRET_KEY="your-secret-key"
$env:VOICECANVAS_MINIO_SECURE="false"
```

素材对象路径统一放在 `catalog/commerce/` 前缀下，例如：

```text
catalog/commerce/food-drink/bubble-tea.png
catalog/commerce/digital/smartphone.png
```

前端不会直连 MinIO。页面根据 `render-catalog.json` 中的 `assetPath` 调用：

```text
GET /api/assets/catalog?path=catalog/commerce/food-drink/bubble-tea.png
```

后端返回代理 URL，图片读取失败时前端会显示 `generated_asset` 占位，创作流程不中断。

长期记忆后端 MVP 测试：

```powershell
cd backend
uv run --no-editable pytest tests/test_user_memory_repository.py tests/test_user_memory_service.py tests/test_memory_extractor.py tests/test_user_memory_api.py tests/test_orchestration_service.py tests/test_llm_command_planner.py
```

长期记忆接入编排主链路未新增第三方依赖；实现复用现有 FastAPI、Pydantic、Planner 和本地 JSON 仓储能力。

后端本地服务：

```powershell
cd backend
$env:PYTHONPATH="src"
uv run --no-editable uvicorn voicecanvas.api.main:app --reload
```

健康检查：

```text
http://127.0.0.1:8000/health
```

后端真实编排 API 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/orchestrations" `
  -ContentType "application/json" `
  -Body '{"projectId":"project_demo","userInput":"创建一个三镜头的珍珠奶茶带货分镜"}'
```

当前 `/api/orchestrations` 会同步返回最新 `project`、`patches`、`history`、`events` 和 `summary`。该接口已经接入后端 `CommandValidator`、`CommandExecutor`、`HistoryManager`、SQLite 项目仓储和长期记忆上下文；自然语言理解默认可使用 `DemoCommandPlanner`，也可通过 `.env` 启用 DeepSeek 真实 LLM Planner。真实 LLM 输出会先经过 Pydantic 结构校验和业务命令校验，失败时重试并按配置降级。

新建项目 API 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/projects" `
  -ContentType "application/json" `
  -Body '{"title":"未命名项目","mode":"storyboard"}'
```

项目状态 API 示例：

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/projects/project_demo_voicecanvas"
```

导出项目包 API 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/projects/project_demo_voicecanvas/export" `
  -ContentType "application/json" `
  -Body '{"format":"json","scope":"project"}'
```

导出当前分镜图片 API 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/projects/project_demo_voicecanvas/export" `
  -ContentType "application/json" `
  -Body '{"format":"png","scope":"active_scene"}'
```

导出的 `.voicecanvas.json` 项目包可通过前端“设置 -> 载入项目”重新载入，也可调用后端载入接口。载入入口只接受 JSON 项目文件；PNG 仅用于图片交付，不能用于恢复可编辑项目状态：

```powershell
$payload = Get-Content ".\VoiceCanvas-Demo.voicecanvas.json" -Raw | ConvertFrom-Json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/projects/import" `
  -ContentType "application/json" `
  -Body (@{ payload = $payload } | ConvertTo-Json -Depth 80)
```

本次新建、导出和载入功能未新增第三方依赖；图片导出使用浏览器原生 `Canvas`、`Blob` 和 `URL.createObjectURL`，后端导出兜底使用 Python 标准库生成可验证 SVG 源。

## 当前状态

项目处于 MVP 主链路落地阶段，当前仓库已提交产品决策、语音指令语料、基础 README、技术架构设计、接口与数据模型设计、前端交互原型与接口绑定设计。当前技术路线已确定为“可恢复 AI 编排器架构”：所有用户语音或文本输入统一进入后端 AI Orchestrator，由 LangGraph 根据上下文推进计划、命令执行、工具调用、澄清等待和恢复继续；当需要澄清时，系统暂停当前任务会话，等待用户语音或点击回答后从原状态继续执行。

当前已完成后端应用层命令闭环，并将 `/api/orchestrations` 接入真实业务执行链路：请求会通过 Demo Planner 生成结构化命令，再经过 Command Validator、Command Executor、History Manager 和 SQLite Project Repository，最终返回真实 Project State、CanvasPatch、HistoryEntry、运行事件和本轮总结。页面交互上，左侧为画布历史区，展示镜头历史、操作历史和关键变更记录；右侧为 AI 交互栏，承载语音入口、当前阶段、澄清问题、执行进度和本轮变更总结；主画布支持随命令执行流式更新。当前前端原型位于 `frontend/`，后端服务位于 `backend/`。

后续将继续补充：

- 真实 LLM Orchestrator 与可恢复会话模块
- SSE Orchestration Event 与画布流式更新模块
- 左侧画布历史区
- 右侧 AI 交互栏
- 用户长期记忆模块
- AI 工具调用模块
- 测试用例与运行方式

## 成功指标

Demo 至少稳定展示：

- 语音创建一个三镜头带货分镜
- 创建过程中画布逐步更新，而不是等待全部任务结束后一次性刷新
- 每个镜头生成草图、字幕/旁白、镜头说明和画面说明
- 语音添加商品、人物、标签、文字、箭头或连接线
- 语音修改指定元素
- 左侧画布历史区展示镜头历史、操作历史和关键变更记录
- 右侧 AI 交互栏展示当前执行阶段、澄清问题和本轮变更总结
- 用户长期记忆能保存并复用命名、布局和风格偏好
- 语音新增、删除或切换镜头
- 语音撤销一次错误操作
- 导出图片和 JSON

工程侧要求：

- AI 编排、可恢复会话、画布状态、命令执行、历史记录、导出模块保持解耦
- 画布流式更新不能绕过命令校验和命令执行器
- 左侧画布历史区只订阅历史和增量事件，不直接修改画布状态
- 右侧 AI 交互栏只订阅运行事件，不直接修改画布状态
- 用户长期记忆与当前项目状态分离，低置信度偏好需要确认后写入
- 每个核心模块都要有可运行测试
- 普通编辑操作不依赖生图模型
- 未知元素有明确降级策略
- 高频指令从识别完成到画布更新，目标响应在 1 秒内
