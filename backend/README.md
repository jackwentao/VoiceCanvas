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

## Docker 运行

仓库根目录提供后端 API 镜像 Dockerfile：

```powershell
docker build -t voicecanvas-backend .
docker run --rm -p 8000:8000 voicecanvas-backend
```

镜像内默认使用 `/app/backend/data/voicecanvas.sqlite3` 保存 Project State，并拷入后端运行时需要的 `frontend/src/prototype/render-catalog.json`。如需连接真实 LLM 或 MinIO，可在 `docker run` 时继续通过 `-e` 传入 `VOICECANVAS_*` 环境变量。

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

项目状态默认使用 SQLite 持久化到 `backend/data/voicecanvas.sqlite3`，服务重启后仍可通过同一个 `projectId` 读取。需要隔离演示或测试数据时，可覆盖数据库路径：

```powershell
$env:VOICECANVAS_PROJECT_DB_PATH="D:\tmp\voicecanvas.sqlite3"
```

该能力使用 Python 标准库 `sqlite3`，没有新增第三方依赖。长期记忆当前仍使用独立 JSON 仓储，后续按单独 PR 迁移。

长期记忆管理接口：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/users/user_1/memories" `
  -ContentType "application/json" `
  -Body '{"kind":"style_preference","content":"用户喜欢清爽绿色和大面积留白","scope":"commerce"}'

Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/users/user_1/memories?includeInactive=true"
```

前端原型的“设置 / 长期记忆”入口会调用：

- `GET /api/users/{userId}/memories`：查看长期记忆。
- `POST /api/users/{userId}/memories`：显式新增 active 记忆。
- `PATCH /api/memories/{memoryId}`：修改内容、类型、范围、置信度或状态。
- `DELETE /api/memories/{memoryId}`：删除长期记忆。

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

## MinIO 素材包初始化

后端通过 `/api/assets/catalog` 和 `/api/assets/catalog/raw` 代理读取 `render-catalog.json` 中声明的 MinIO 素材。配置好 MinIO 环境变量后，先下载真实素材包，再上传到桶内：

```powershell
$env:VOICECANVAS_ASSET_PROVIDER="minio"
$env:VOICECANVAS_MINIO_ENDPOINT="127.0.0.1:9000"
$env:VOICECANVAS_MINIO_BUCKET="voicecanvas-assets"
$env:VOICECANVAS_MINIO_ACCESS_KEY="your-access-key"
$env:VOICECANVAS_MINIO_SECRET_KEY="your-secret-key"
$env:VOICECANVAS_MINIO_SECURE="false"

uv run --no-editable python scripts/download_real_catalog_assets.py --overwrite
uv run --no-editable python scripts/seed_minio_catalog.py --asset-root ".\data\real-assets"
uv run --no-editable python scripts/check_minio_catalog.py --strict
```

`download_real_catalog_assets.py` 会把 8 个公开 PNG 素材下载到 `backend/data/real-assets`，来源为 Google Noto Emoji，许可证为 Apache-2.0。`seed_minio_catalog.py --asset-root` 会按 `catalog/commerce/...` 相对路径上传真实素材。`check_minio_catalog.py --strict` 会逐个检查桶内对象；任意素材缺失时返回非 0 状态。

当 `VOICECANVAS_ASSET_PROVIDER=minio` 时，`uvicorn voicecanvas.api.main:app` 的默认启动路径也会执行同一套 MinIO 素材完整性检查。素材包未上传完整时后端不会启动，并会列出缺失对象路径。仅本地调试临时跳过时可设置：

```powershell
$env:VOICECANVAS_SKIP_MINIO_CATALOG_CHECK="true"
```

如果比赛现场只需要先跑通代理链路，可使用 `uv run --no-editable python scripts/seed_minio_catalog.py --generate-placeholders` 生成占位 PNG，但正式演示素材以真实下载包为准。

长期记忆后端 MVP 未新增第三方依赖，复用 Pydantic 进行领域模型校验，使用 Python 标准库 `json` 和 `pathlib` 实现本地 JSON 仓储。原创功能边界：

- 长期记忆领域模型，记录偏好类型、作用范围、置信度、状态、来源证据和最近使用时间。
- `UserMemoryRepository` 仓储协议和本地 JSON 仓储实现，方便后续替换为数据库或云端存储。
- `UserMemoryService` 状态流转与相关性检索，确保只有 active 记忆进入 Planner 上下文。
- `MemoryExtractor` 候选提取和敏感信息过滤，避免低置信或隐私内容静默写入长期记忆。

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
uv run --no-editable pytest tests/test_user_memory_repository.py tests/test_user_memory_service.py tests/test_memory_extractor.py tests/test_user_memory_api.py
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


## 工作台固定接口

页面使用固定的工作台查询和动作接口，不需要构造领域命令。所有动作均由后端
创建命令，经过既有校验器与执行器，再保存项目、撤销重做历史、待澄清任务和用量。
SQLite 默认保存 `projects` 与 `workspace_runtime`；用户偏好继续由后端记忆仓储保存。
语义素材目录位于 `src/voicecanvas/resources/render-catalog.json`，后端运行和镜像构建
不再依赖前端目录。接口与复现方式见 [工作台接口](../docs/工作台接口.md)。

```powershell
uv run --no-editable pytest tests/test_workspace_api.py tests/test_api.py tests/test_history_manager.py
```
