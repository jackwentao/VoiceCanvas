# VoiceCanvas 部署与联调

[返回项目首页](../README.md)

各命令均注明执行目录。启用 MinIO 或真实 LLM 前，先完成首页的本地 Demo。

## MinIO 素材包启动

比赛现场如果要验证后端代理 MinIO 素材链路，可用 Docker 启动 MinIO。

### 1. 启动 MinIO

```powershell
docker run --rm --name voicecanvas-minio `
  -p 9000:9000 `
  -p 9001:9001 `
  -e MINIO_ROOT_USER=voicecanvas `
  -e MINIO_ROOT_PASSWORD=voicecanvas123 `
  quay.io/minio/minio server /data --console-address ":9001"
```

MinIO 控制台：

```text
http://127.0.0.1:9001
```

### 2. 配置后端环境变量

```powershell
cd backend
$env:VOICECANVAS_ASSET_PROVIDER="minio"
$env:VOICECANVAS_MINIO_ENDPOINT="127.0.0.1:9000"
$env:VOICECANVAS_MINIO_BUCKET="voicecanvas-assets"
$env:VOICECANVAS_MINIO_ACCESS_KEY="voicecanvas"
$env:VOICECANVAS_MINIO_SECRET_KEY="voicecanvas123"
$env:VOICECANVAS_MINIO_SECURE="false"
```

### 3. 下载并上传 Render Catalog 素材

```powershell
uv run --no-editable python scripts/download_real_catalog_assets.py --overwrite
uv run --no-editable python scripts/seed_minio_catalog.py --asset-root ".\data\real-assets"
uv run --no-editable python scripts/check_minio_catalog.py --strict
```

素材路径统一位于 `catalog/commerce/` 前缀下，例如：

```text
catalog/commerce/food-drink/bubble-tea.png
catalog/commerce/digital/smartphone.png
```

后端启动时如果 `VOICECANVAS_ASSET_PROVIDER=minio`，会默认检查素材包完整性；缺失任意 Catalog 素材时服务会拒绝启动并列出缺失路径。临时调试时可设置：

```powershell
$env:VOICECANVAS_SKIP_MINIO_CATALOG_CHECK="true"
```

## Docker 验证后端

仓库根目录提供后端 Dockerfile。

```powershell
docker build -t voicecanvas-backend .
docker run --rm --name voicecanvas-backend -p 8000:8000 `
  -e VOICECANVAS_PROJECT_DB_PATH=/app/backend/data/voicecanvas.sqlite3 `
  voicecanvas-backend
```

如果需要让容器后端连接宿主机 MinIO，可使用 `host.docker.internal:9000`：

```powershell
docker run --rm --name voicecanvas-backend -p 8000:8000 `
  -e VOICECANVAS_ASSET_PROVIDER=minio `
  -e VOICECANVAS_MINIO_ENDPOINT=host.docker.internal:9000 `
  -e VOICECANVAS_MINIO_BUCKET=voicecanvas-assets `
  -e VOICECANVAS_MINIO_ACCESS_KEY=voicecanvas `
  -e VOICECANVAS_MINIO_SECRET_KEY=voicecanvas123 `
  -e VOICECANVAS_MINIO_SECURE=false `
  voicecanvas-backend
```

前端仍按本地方式启动，并访问 `http://127.0.0.1:4178/index.html`。

## 真实 LLM 配置

默认 Demo Planner 不需要 API Key。需要验证真实模型时：

```powershell
cd backend
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

| 模式 | 说明 |
| --- | --- |
| `demo` | 默认模式，使用本地确定性演示 Planner，适合离线评审和录屏 |
| `llm` | 只使用真实 LLM，失败后返回错误，不自动降级 |
| `hybrid` | 优先真实 LLM，额度不足、网络失败、超时、格式错误或业务校验失败后降级到 Demo Planner |

真实 LLM 只负责把自然语言转成结构化命令；所有写操作仍必须经过 Pydantic 结构校验、`CommandValidator` 和 `CommandExecutor`，不能直接覆盖 Project State。

## 常用 API 验证

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/orchestrations" `
  -ContentType "application/json" `
  -Body '{"projectId":"project_demo_voicecanvas","userInput":"创建一个三镜头的珍珠奶茶带货分镜，主打低糖和新品上市"}'
```

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/projects/project_demo_voicecanvas"
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/projects/project_demo_voicecanvas/export" `
  -ContentType "application/json" `
  -Body '{"format":"json","scope":"project"}'
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/projects/project_demo_voicecanvas/export" `
  -ContentType "application/json" `
  -Body '{"format":"png","scope":"active_scene"}'
```

SSE 流式编排：

```powershell
$body = @{
  projectId = "project_demo_voicecanvas"
  userInput = "创建一个三镜头的珍珠奶茶带货分镜，主打低糖和新品上市"
} | ConvertTo-Json -Compress

curl.exe -N `
  -X POST "http://127.0.0.1:8000/api/orchestrations/stream" `
  -H "Content-Type: application/json" `
  --data $body
```
