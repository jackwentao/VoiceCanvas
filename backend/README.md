# VoiceCanvas Backend

VoiceCanvas 后端使用 Python、uv、FastAPI、LangGraph 和 Pydantic 构建。

## 运行

```powershell
uv sync --no-editable
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

当前接口同步返回：

- `project`：执行后的可信 Project State。
- `patches`：本轮命令产生的 CanvasPatch。
- `history`：已记录的 HistoryEntry。
- `events`：阶段、画布 Patch 和本轮总结事件。
- `summary`：本轮是否完成及执行命令数量。

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
