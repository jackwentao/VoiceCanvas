# VoiceCanvas Backend

VoiceCanvas 后端使用 Python、uv、FastAPI、LangGraph 和 Pydantic 构建。

## 运行

```powershell
uv sync --no-editable
$env:PYTHONPATH="src"
uv run --no-editable uvicorn voicecanvas.api.main:app --reload
```

默认访问：

```text
http://127.0.0.1:8000/health
```

真实编排接口：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/orchestrations" `
  -ContentType "application/json" `
  -Body '{"projectId":"project_demo","userInput":"创建一个三镜头的珍珠奶茶带货分镜"}'
```

项目状态接口：

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/projects/project_demo"
```

当前接口同步返回：

- `project`：执行后的可信 Project State。
- `patches`：本轮命令产生的 CanvasPatch。
- `history`：已记录的 HistoryEntry。
- `events`：阶段、画布 Patch 和本轮总结事件。
- `summary`：本轮是否完成及执行命令数量。

`GET /api/projects/{projectId}` 返回当前可信 `project`、该项目 `history` 和可扩展的 `events` 数组，前端原型启动时用它初始化画布、历史区和 AI 交互栏状态。

流式编排接口：

```powershell
$body = @{
  projectId = "project_demo"
  userInput = "创建一个三镜头的珍珠奶茶带货分镜"
} | ConvertTo-Json -Compress

curl.exe -N `
  -X POST "http://127.0.0.1:8000/api/orchestrations/stream" `
  -H "Content-Type: application/json" `
  --data $body
```

`POST /api/orchestrations/stream` 使用 `text/event-stream` 返回 SSE：

- `event: orchestration.event`：阶段变化、画布 Patch、澄清请求和本轮总结等即时事件；复杂命令会在每条命令执行并产生 Patch 后立刻返回。
- `event: orchestration.result`：本轮最终完整结果，结构与同步 `POST /api/orchestrations` 响应一致，便于前端在流结束时收口同步状态。

前端原型默认连接 `http://127.0.0.1:8000`；如果新版后端临时跑在其他端口，可以通过查询参数切换：

```text
http://127.0.0.1:4178/index.html?apiBaseUrl=http://127.0.0.1:8001
```

本功能未新增第三方依赖，复用项目既有依赖与浏览器原生能力：

- FastAPI / Starlette：提供 `StreamingResponse`，仅负责 HTTP `text/event-stream` 传输边界。
- Pydantic：继续负责 `Project`、`CanvasElement`、`CanvasPatch` 等领域模型校验。
- 浏览器 Fetch / ReadableStream：前端原型消费 SSE 文本流，不引入额外前端框架。

原创功能边界：

- 后端原创实现 `orchestration.event` / `orchestration.result` 事件协议，按画布 Patch 粒度推送复杂命令执行结果。
- 后端原创实现 LLM 命令归一化，把同批新增元素名称引用转换为合法 `connector.from` / `connector.to`。
- 前端原创实现流式事件消费与画布状态投影，把收到的 Patch 逐步应用到本地 Project State。

说明：默认自然语言理解由 `DemoCommandPlanner` 覆盖比赛演示语料；设置环境变量后可启用真实 LLM Planner，并在失败时重试、提醒错误原因，再按配置降级。

## 真实 LLM Planner

真实 LLM 只负责把用户输入转换为结构化命令，不直接覆盖 `Project`。后端会先用 Pydantic 校验 LLM JSON 输出，再用 `CommandValidator` 校验命令是否能在当前项目执行，最后才交给 `CommandExecutor`。

```powershell
$env:VOICECANVAS_PLANNER="hybrid"
$env:VOICECANVAS_LLM_BASE_URL="https://你的-openai-compatible-endpoint/v1"
$env:VOICECANVAS_LLM_MODEL="你的模型名"
$env:VOICECANVAS_LLM_API_KEY="你的 API Key"
$env:VOICECANVAS_LLM_MAX_ATTEMPTS="3"
$env:VOICECANVAS_LLM_TIMEOUT_SECONDS="20"
$env:PYTHONPATH="src"
uv run --no-editable uvicorn voicecanvas.api.main:app --reload
```

Planner 模式：

- `demo`：默认模式，只使用本地 Demo Planner。
- `llm`：只使用真实 LLM；重试后仍失败会返回错误提醒，不执行降级命令。
- `hybrid`：优先真实 LLM；额度不足、网络失败、超时、格式错误或业务校验失败且重试耗尽后，降级到 Demo Planner，并在响应事件中返回 `PLANNER_WARNING`。

真实 LLM 输出验收测试默认跳过。需要真实调用时显式开启：

```powershell
$env:VOICECANVAS_RUN_REAL_LLM_TESTS="1"
$env:VOICECANVAS_LLM_BASE_URL="https://你的-openai-compatible-endpoint/v1"
$env:VOICECANVAS_LLM_MODEL="你的模型名"
$env:VOICECANVAS_LLM_API_KEY="你的 API Key"
uv run --no-editable pytest tests/test_real_llm_command_planner.py -s
```

真实 LLM 增删改查冒烟验收：

```powershell
$env:PYTHONPATH="src"
$env:PYTHONIOENCODING="utf-8"
$env:VOICECANVAS_PLANNER="llm"
$env:VOICECANVAS_LLM_MAX_ATTEMPTS="2"
$env:VOICECANVAS_LLM_TIMEOUT_SECONDS="45"
uv run --no-editable python scripts\real_llm_crud_smoke.py
```

该脚本会连续调用创建分镜、切换镜头、新增元素、修改元素、删除元素、删除镜头、撤销和重做，输出每一步的状态、Patch 类型、History 数量和事件类型，便于确认真实模型是否能驱动画布命令闭环。

测试会使用规定好的真实命令：

- `创建一个三镜头的珍珠奶茶带货分镜`
- `加标题，写新品上市`
- `把标题改成低糖也好喝`

每次真实测试会把 LLM 原始输出、最终命令、重试次数和分析保存到：

```text
backend/artifacts/llm/<timestamp>/
```

其中每个用例有独立 JSON 文件，并生成 `summary.md` 便于人工复盘。

## 测试

```powershell
uv run --no-editable pytest
uv run --no-editable pytest tests/test_api.py tests/test_orchestration_service.py
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

说明：当前项目路径包含中文，`uv run --no-editable` 可以避免 Windows 下 editable 安装生成的 `.pth` 路径编码问题。

## 目录职责

- `api/`：FastAPI 路由、请求响应模型和后续 SSE 入口。
- `graph/`：LangGraph 编排流程骨架，负责计划、工具调用、命令执行、澄清和总结的流转。
- `application/`：命令校验、命令执行、历史撤销重做、Demo Planner、内存项目仓库和编排服务。
- `domain/`：Pydantic 领域模型与纯业务规则。
- `adapters/`：LLM、ASR、七牛云、导出和存储适配器。
- `infrastructure/`：配置、日志、HTTP、持久化等基础设施。
