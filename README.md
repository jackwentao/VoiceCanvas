# VoiceCanvas

**用语音持续创建、编辑和导出分镜草图。** 面向内容创作者的可编辑分镜原型，参赛题目为七牛云 XEngineer「AI 语音绘图工具」。

[演示视频](https://www.bilibili.com/video/BV1yDJA6eEjv/) · [部署与联调](docs/DEPLOYMENT.md) · [运行架构](docs/ARCHITECTURE.md) · [测试指南](docs/TESTING.md)

## 功能与边界

- 创建分镜、切换镜头，添加或修改文字、商品、标签、箭头和连接线。
- 对不明确的指代发起澄清；支持撤销、重做和清空确认。
- 导出 PNG 与项目 JSON，从 JSON 恢复编辑；SQLite 保存项目状态。
- 使用本地 Demo Planner，或通过适配器接入真实 LLM；提供用户偏好记忆 MVP。

首次使用需点击按钮授予麦克风权限。语音识别与播报使用浏览器原生能力，支持情况取决于浏览器与网络。普通画布编辑使用结构化命令；未知对象使用占位，复杂生图、精细图层编辑与多人协作不在当前 MVP 范围内。完整边界见[指令验收](docs/Demo脚本与指令能力验收.md)。

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

打开 [前端](http://127.0.0.1:4178/index.html)，后端健康检查为 [GET /health](http://127.0.0.1:8000/health)。可先点击画布内的示例提示，将指令填入输入框并发送，再尝试语音创建分镜、修改文字和导出。

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
npm run test:prototype
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

新版采用镜头缩略图、大画布、底部语音输入与可收起的助手面板。顶部可导出 PNG/JSON，
左侧可以新建、切换和载入项目；支持 `Alt+V` 开关语音、`Ctrl+Z` 撤销、
`Ctrl+Shift+Z` 重做，输入框 `Enter` 发送、`Shift+Enter` 换行。

前端只展示后端快照和处理输入，不再提供本地业务执行或离线假成功。项目、镜头、
操作历史、澄清、用量及偏好由后端控制与保存；离线时明确提示并提供重新连接。
页面按钮使用[固定工作台接口](docs/工作台接口.md)，自然语言使用既有编排接口。

本次工作台使用原生 HTML/CSS/JavaScript、浏览器原生语音、SVG/Canvas 展示与下载，
没有新增框架或外部设计服务依赖。业务执行、可信状态和存储均属于项目原创实现，
第三方 LLM 只通过既有适配器提供理解能力。完整边界见[依赖声明](docs/技术选型与依赖声明.md)。

```powershell
npm --prefix frontend run test:prototype
```

该命令运行既有原型契约/语音回归和新增的工作台状态边界测试。后端验证与页面手动
验收步骤见[工作台使用与验收](docs/工作台使用与验收.md)。
