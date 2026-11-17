# VoiceCanvas

## 自由 SVG 分镜工作台

前端以 main 的手绘纸张首页和三栏画桌为基础。打开 `http://127.0.0.1:4178/index.html`，点击“开始我的创作”，通过分镜 API 创建项目并进入 `workspace.html?board=…`；也可直接进入工作台恢复上次项目。左侧管理分镜，中间预览画面，底部输入语音或文字，右侧展示处理反馈与删除确认。

点击输入框左侧麦克风并授权，可连续说“新建两个镜头”“切换到第二个镜头”“当前镜头改名为雨夜”“把第三个镜头移到第一位”。每个镜头独立保存画面与修改历史；删除需确认，可用“撤销分镜操作”恢复。语音和文字交给自主工具调用 Agent 决定如何拆镜、管理及生成 SVG；直接点击管理按钮不调用模型。画面由外部模型生成，可自然语言改画，也可点击“编辑文字”即时改字、字号和换行后保存。导出当前镜头 PNG / SVG。

先在 `backend` 将 `.env.example` 复制为 `.env`，配置 `VOICECANVAS_SHOT_LLM_API_KEY`、`VOICECANVAS_SHOT_LLM_BASE_URL` 与 `VOICECANVAS_SHOT_LLM_MODEL`。验证端点为 `https://api.commandcode.ai/provider/v1`，模型为 `deepseek/deepseek-v4.1-flash`；支持替换兼容服务。默认输出预算 32768、超时 300 秒，无自动付费重试，失败保留上一画面。无密钥可测试结构化管理按钮；自然语言 Agent 和真实绘图需要配置，并要求模型支持 tools。静态服务只使用 Node 内置模块，无需为该入口安装 npm 包。

工作台统一使用 `board` 定位自由分镜项目。已移除旧页面、旧项目分流及单镜头迁移入口；未接入的 JSON 导入导出、偏好记忆和整体背景控件已从页面移除。

语音识别和播报由浏览器 Web Speech API 提供，可能依赖联网服务；不支持时可输入同样的指令。项目原创部分是 SVG 校验、受限编辑协议、持久化、独立历史与语音编排；画面生成由外部模型提供，人物肢体和文字可读性仍需看图检查。内置绘图 skill 的来源及许可证见 [绘图技能接入](docs/绘图技能接入.md)。

操作与限制见 [语音分镜管理](docs/语音分镜管理.md)，接口见 [分镜项目 API](docs/分镜项目API.md)，配置及文字编辑见 [单镜头创作](docs/单镜头创作.md)。[main 工作台适配验收](docs/main工作台分镜适配.md) 包含无在线模型的浏览器验收命令和截图。此前的 [人物提示实验](docs/experiments/subject-quality-20261117/README.md)、[视觉反馈实验](docs/experiments/visual-review-20261117/README.md) 与 [分镜文字实测](docs/experiments/storyboard-text-20261117/README.md) 保留原始效果与边界。

**用语音持续创建、编辑和导出分镜草图。** 面向内容创作者的可编辑分镜原型，参赛题目为七牛云 XEngineer「AI 语音绘图工具」。

[演示视频](https://www.bilibili.com/video/BV1yDJA6eEjv/) · [部署与联调](docs/DEPLOYMENT.md) · [运行架构](docs/ARCHITECTURE.md) · [测试指南](docs/TESTING.md)

## 功能与边界

自然语言统一接入自主工具调用 Agent，已删除旧 `/command` 正则路由。Agent 决定工具和执行顺序，任务逐镜保存，刷新继续查看，完成前核对实际镜头数量与时长。详见 [分镜 Agent](docs/分镜Agent.md)。后台任务使用单个 Uvicorn 进程，不要启用多 worker。

绘图默认关闭当前网关的深度思考（`VOICECANVAS_SHOT_REASONING_EFFORT=off`），同题两次实测 16.7/20.8 秒，对照 123.4 秒；完整输出后才显示画面。没有减少自由绘图能力或输出预算，动作准确性仍需验收。其他供应商不支持该参数时可显式设为 `provider-default`。真实咖啡店三镜头业务模拟的失败项、全部用量和对比图见 [提速与业务验收](docs/experiments/drawing-latency-20261117/README.md)。

输入提交后会显示绘图等待时间；失败显示原因并保留输入和已有画面。若返回相同画面会提示“没有变化”。发现输入没有效果时，先检查是否误连固定响应测试服务及绘图网络配置，见 [输入无效果排查](docs/输入无效果排查.md)。

当前支持独立镜头绘制与编辑、语音分镜管理、直接改字、删除确认、画面与编排的独立撤销、持久化和 PNG/SVG 导出。完整故事可由 Agent 自主拆镜绘制，支持整组下载请求与复合语音操作；跨镜头角色一致性和动作准确性仍需视觉验收。首次语音使用需授权麦克风。

## 快速开始

准备 Python 3.11+、uv、Node.js 20+ 和 npm。以下两个终端都从**仓库根目录**开始。

终端 1：启动后端。

```powershell
cd backend
uv sync --no-editable
$env:PYTHONPATH="src"
uv run --no-editable uvicorn voicecanvas.api.main:app --reload
```

终端 2：启动前端。

```powershell
cd frontend
npm install
npm run prototype
```

打开 [手绘画廊首页](http://127.0.0.1:4178/index.html)，后端健康检查为 [GET /health](http://127.0.0.1:8000/health)。首页可以分类浏览和放大查看作品；点击“开始我的创作”由后端创建项目后进入工作台。也可直接打开 [工作台](http://127.0.0.1:4178/workspace.html)，再尝试语音创建分镜、修改文字和导出。

## 配置

| 配置 | 默认行为 |
| --- | --- |
| `VOICECANVAS_PLANNER=demo` | 本地确定性 Planner，无需模型密钥 |
| `VOICECANVAS_ASSET_PROVIDER=local` | 本地素材或占位，无需 MinIO |
| 项目状态 | 保存到 `backend/data/voicecanvas.sqlite3` |
| 用户偏好 | 保存到 `backend/data/user-memory.json` |

前端默认连接 `http://127.0.0.1:8000`；可通过 `?apiBaseUrl=http://127.0.0.1:8001` 更换地址。真实 LLM 的 `demo / llm / hybrid` 模式、MinIO 素材初始化、Docker 和 API/SSE 示例见[部署与联调](docs/DEPLOYMENT.md)。

## 验证

前端契约测试，在仓库根目录执行：

```powershell
cd frontend
npm test
```

后端测试与质量检查，在另一个位于仓库根目录的终端执行：

```powershell
cd backend
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

重点链路与真实 LLM 验收命令见[测试指南](docs/TESTING.md)。

## 目录与文档

```text
frontend/    HTML / CSS / JavaScript 原型、语音会话、画布投影、导出
backend/     FastAPI / LangGraph、可信状态、命令校验、存储适配
docs/        产品决策、接口契约、部署、测试与指令验收
Dockerfile   后端 API 镜像
```

- [运行架构与数据流](docs/ARCHITECTURE.md)
- [技术架构设计](docs/技术架构设计.md) · [接口与数据模型](docs/接口与数据模型设计.md)
- [指令完成情况](docs/指令完成情况.md) · [语音指令语料](docs/语音指令语料.md)
- [前端交互与接口绑定](docs/前端交互原型与接口绑定设计.md)
- [长期记忆 MVP](docs/长期记忆MVP决策.md) · [产品决策](docs/产品决策记录.md)
- [技术选型与依赖声明](docs/技术选型与依赖声明.md) · [PR 记录](docs/PR提交记录.md)
- [协作规则](AGENTS.md)

## 依赖边界

| 位置 | 依赖 | 用途与边界 |
| --- | --- | --- |
| `frontend/package.json` | `express` | 本地原型静态服务 |
| `frontend/package.json` | `cors`、`zod` | 本地跨端口调试和前端契约校验准备 |
| `frontend/package.json` | `typescript`、`tsx`、`vitest`、`supertest` | 前端脚本、类型和测试工具 |
| `backend/pyproject.toml` | `fastapi`、`uvicorn[standard]` | 后端 HTTP API 与本地服务运行 |
| `backend/pyproject.toml` | `pydantic` | 领域模型、请求响应和命令校验 |
| `backend/pyproject.toml` | `langgraph`、`langchain-core` | 可恢复 AI 编排和 LLM 适配基础类型 |
| `backend/pyproject.toml` | `httpx`、`python-dotenv` | 外部 HTTP 调用与环境变量加载 |
| `backend/pyproject.toml` | `minio` | MinIO 素材读取适配器，仅在存储层使用 |
| `backend/pyproject.toml` | `pytest`、`pytest-asyncio`、`respx`、`ruff`、`mypy` | 后端测试、Mock、lint 和类型检查 |
| Python 标准库 | `sqlite3`、`json`、`pathlib` | Project State 和长期记忆本地持久化 |
| 浏览器原生 API | Web Speech API、SpeechSynthesis、Canvas、Blob、Fetch、ReadableStream | 语音入口、播报、画布导出、SSE 消费，不参与后端可信状态判断 |
| 外部服务 | OpenAI-compatible LLM API | 可选真实 Planner，失败可降级到 Demo Planner |
| 外部服务 | MinIO | 可选素材桶验证，前端不直连 MinIO，不接触存储凭证 |

第三方框架只作为服务运行、模型校验、编排基础设施、存储适配和测试工具使用；VoiceCanvas 的业务规则、画布状态变更、命令语义、导出闭环和演示工作流为本项目原创实现。


## 创作工作台

`index.html` 读取后端原创展示画廊，点击创作后创建空白分镜项目；`workspace.html?board=…` 是统一工作台。
页面只接入 `/api/storyboards` 和 `/api/shots` 完成分镜与画面操作。
支持 `Alt+V` 开关语音、`Ctrl+Z` 撤销当前画面、`Ctrl+Shift+Z` 重做，输入框 `Enter` 发送、`Shift+Enter` 换行。
操作反馈与删除确认显示在右侧助手，运行与浏览器测试见 [工作台适配](docs/main工作台分镜适配.md)。
