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

## 测试

```powershell
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

说明：当前项目路径包含中文，`uv run --no-editable` 可以避免 Windows 下 editable 安装生成的 `.pth` 路径编码问题。

## 目录职责

- `api/`：FastAPI 路由、请求响应模型和 SSE 入口。
- `graph/`：LangGraph 编排流程，负责计划、工具调用、命令执行、澄清和总结的流转。
- `application/`：命令校验、命令执行、工具运行、会话和事件服务。
- `domain/`：Pydantic 领域模型与纯业务规则。
- `adapters/`：LLM、ASR、七牛云、导出和存储适配器。
- `infrastructure/`：配置、日志、HTTP、持久化等基础设施。
