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

说明：本阶段自然语言理解由 `DemoCommandPlanner` 覆盖比赛演示语料，暂未接真实 LLM、ASR、SSE 和持久化数据库。

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
