# VoiceCanvas 后端

FastAPI 提供分镜、画面、Agent 任务和只读预览 API。当前创作使用自由 SVG 工具调用 Agent，运行单个 Uvicorn 进程；模型、渲染器和仓储通过协议接入。

从仓库根目录按[部署指南](../docs/DEPLOYMENT.md)准备环境。在本目录启动：

```powershell
uv sync --frozen --no-editable
$env:PYTHONPATH="src"
uv run --frozen --no-editable uvicorn voicecanvas.api.main:app --host 127.0.0.1 --port 8000
```

先复制并编辑 `.env.example`，填入模型密钥；已有 `.env` 时保留。当前验证 `deepseek/deepseek-v4.1-flash`，密钥仅留在后端。默认数据库为 `data/svg-shots.sqlite3`。

| 目录 | 作用 |
| --- | --- |
| `src/voicecanvas/api/` | HTTP 协议与错误映射 |
| `src/voicecanvas/application/` | 分镜、镜头、Agent、预览服务及端口 |
| `src/voicecanvas/domain/` | 领域状态、SVG/文字校验与受限修改 |
| `src/voicecanvas/adapters/` | 模型 HTTP、内置作画知识、浏览器渲染 |
| `src/voicecanvas/infrastructure/` | SQLite、配置及图片缓存 |
| `tests/` | 离线回归与浏览器专用 fixture |

完整 HTTP 类型可访问 `/docs`。[API 说明](../docs/API.md)

```powershell
uv run --frozen --no-editable pytest -q
uv run --frozen --no-editable ruff check .
uv run --frozen --no-editable mypy src
```

[架构](../docs/ARCHITECTURE.md) · [测试分组与现场验收](../docs/TESTING.md) · [依赖及原创边界](../docs/技术选型与依赖声明.md)
