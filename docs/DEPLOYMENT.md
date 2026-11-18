# 部署与配置

[项目首页](../README.md) · [使用指南](使用指南.md) · [测试指南](TESTING.md)

## 本地启动

Python 3.11+、uv、Node.js 20+ 为基础运行环境。建议将仓库、虚拟环境、缓存和数据目录放在 D 盘等工作盘。当前前端直接由 Node 内置模块提供静态服务，无需安装 npm 包。

从仓库根目录分别开启两个终端：

```powershell
cd backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，填入模型密钥；不要提交 .env。
uv sync --frozen --no-editable
$env:PYTHONPATH="src"
uv run --frozen --no-editable uvicorn voicecanvas.api.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run prototype
```

打开 `http://127.0.0.1:4178/index.html`，健康检查 `http://127.0.0.1:8000/health`。OpenAPI 位于 `http://127.0.0.1:8000/docs`。运行单个 Uvicorn 进程，不添加 `--workers`；调试时的自动重启会中断正在执行的 Agent 任务。

前端默认 API 为8000；使用其他端口时可打开 `workspace.html?apiBaseUrl=http://127.0.0.1:8001`。后端 CORS 默认允许 localhost/127.0.0.1:4178，更换前端端口或域名需相应调整服务配置。

## 模型与浏览器配置

`backend/.env.example` 是可复制的配置样例。Agent 决策、绘图和专门图片评审共用一份模型配置，当前实测使用：

```dotenv
VOICECANVAS_SHOT_LLM_BASE_URL=https://api.commandcode.ai/provider/v1
VOICECANVAS_SHOT_LLM_MODEL=deepseek/deepseek-v4.1-flash
VOICECANVAS_SHOT_LLM_API_KEY=填入自己的密钥
VOICECANVAS_SHOT_REASONING_EFFORT=off
```

| 变量 | 默认值与用途 |
| --- | --- |
| `VOICECANVAS_SHOT_LLM_BASE_URL`、`VOICECANVAS_SHOT_LLM_MODEL`、`VOICECANVAS_SHOT_LLM_API_KEY` | 模型端点、模型标识和 API 密钥，创作前需要配置 |
| `VOICECANVAS_SHOT_REASONING_EFFORT` | `off`，当前网关关闭思考的有效参数；`provider-default` 表示不发送该字段 |
| `VOICECANVAS_SHOT_MAX_TOKENS` | 32768；绘图输出预算，允许1024–65536 |
| `VOICECANVAS_SHOT_TIMEOUT_SECONDS` | 300秒；绘图超时，允许1–600 |
| `VOICECANVAS_SHOT_DRAWING_SKILL` | `svg-illustration`；`none` 关闭内置作画知识 |
| `VOICECANVAS_SHOT_DB_PATH` | 默认 `backend/data/svg-shots.sqlite3`；可指定工作盘上的绝对路径 |
| `VOICECANVAS_RENDER_BROWSER_PATH` | 可选 Chromium/Edge 可执行文件；Windows 自动寻找系统 Edge，Linux 查找 chromium/google-chrome |
| `VOICECANVAS_SHOT_LOCAL_ADDRESS` | 默认不设置；只在验证 IPv6 可用且 IPv4 TLS 有问题时设置 `::` |

决策和专门评审各有90秒请求超时；专门评审输出预算1800 token。配置在服务初始化时读取，修改后重启后端。模型须支持工具调用；图片评审还要求接口实际支持 `image_url`。工具不可用会返回错误，不回退为固定图或把源码检查冒充看图。

浏览器由部署方提供，产品不会自动下载安装。看图工具使用服务端独立临时 profile；未安装浏览器时基本绘图和管理仍可运行。字体回退会改变中文排版，目标部署环境应具备所需中文字体并实际检查导出。

语音识别和播报使用访问者浏览器的 Web Speech API，可能依赖其联网服务。建议使用支持中文的 Chrome/Edge，通过 localhost 或 HTTPS 访问；没有自研 ASR、离线语音识别或外部 ASR SDK 配置。

## 数据与备份

项目、镜头与 Agent 任务保存在同一个镜头 SQLite 文件。图片缓存位于其同级 `shot-previews/`，临时浏览器目录位于该缓存的 `tmp/`。例如数据库配置为 `D:/VoiceCanvas/data/svg-shots.sqlite3`，图片也保存在 D 盘。

备份时先停止服务，再复制数据库文件；恢复时让 `VOICECANVAS_SHOT_DB_PATH` 指向副本。浏览器仅记录最近项目定位，不能代替数据库备份。图片缓存是派生产物，可在停止服务后清理并由工具重新渲染。当前没有自动缓存淘汰和画面垃圾回收，长期运行需管理磁盘容量。

## Docker 后端

仓库 Dockerfile 只提供后端。以下 PowerShell 命令从仓库根目录运行，先准备有效的 `backend/.env`：

```powershell
docker build -t voicecanvas-backend .
New-Item -ItemType Directory -Force backend/data | Out-Null
docker run --rm --name voicecanvas-backend -p 127.0.0.1:8000:8000 `
  --env-file backend/.env `
  -e VOICECANVAS_SHOT_DB_PATH=/app/backend/data/svg-shots.sqlite3 `
  -v "${PWD}/backend/data:/app/backend/data" `
  voicecanvas-backend
```

前端按本地方式启动。基础镜像没有 Chromium 和中文字体，上述命令仅运行基本 API/绘图；完整视觉工具需要另备具有浏览器、字体和正常沙箱支持的非 root 运行环境，不能把 Windows 浏览器路径传入 Linux 容器。本次文档整理没有验收完整 Docker 视觉部署，也没有增加一键容器化承诺。

## 故障排查

| 现象 | 检查与处理 |
| --- | --- |
| 页面连接失败 | 先请求 `/health`；检查前端 API 地址、端口和 CORS |
| 输入没有实际绘图效果 | 产品后端应为 `voicecanvas.api.main:app`；`browser_fixture:app` 是固定响应测试服务，只供验收 |
| HTTP 401/403、模型错误或连接失败 | 核对密钥、模型名、端点、额度和网络，修改配置后重启；已有画面保留，无自动付费重试 |
| IPv4 TLS 中断 | 先独立确认 IPv6 连通，再尝试 `VOICECANVAS_SHOT_LOCAL_ADDRESS=::`；不关闭证书校验 |
| 渲染浏览器未找到 | 指定有效的服务端浏览器路径，确认服务账号可启动；重新部署后再检查字体与图片 |
| 任务中断 | 检查已经保存的镜头，再提交继续需求；刷新不会自动重放 |

本地运行默认绑定 `127.0.0.1`。公开部署需要自行提供访问控制和任务运行环境。[架构说明](ARCHITECTURE.md)
