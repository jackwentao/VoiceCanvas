# VoiceCanvas

用语音或文字，把故事变成可继续修改的分镜草图。

VoiceCanvas 面向需要向摄影师、剪辑师或团队说明画面想法的内容创作者。用户描述故事、镜头数量、时长和关键动作，Agent 自主选择工具，创建独立镜头并生成自由 SVG；之后可以调整顺序、继续改画、直接修改对白和字幕，导出 PNG 或 SVG。

![VoiceCanvas 分镜工作台实测](docs/experiments/storyboard-agent-20261117/workspace.jpg)

上图来自真实模型的三镜头业务模拟。项目目前是可运行的创作原型，适合表达和讨论镜头意图；复杂人物动作、手与物体接触、跨镜角色一致性仍需人工验收。

## 能做什么

| 用户任务 | 当前能力 |
| --- | --- |
| 描述一段完整故事 | Agent 自主拆镜，保存每镜的拍摄说明、景别和时长；每镜独立生成 |
| 持续调整分镜 | 语音或文字管理镜头、改画、排序、复制；删除前确认 |
| 修改对白、字幕或招牌 | 直接编辑已有 SVG 文字、字号与换行，预览后保存，无需请求模型 |
| 检查关键动作 | Agent 可选用真实图片渲染与同模型看图评审，指出偏差，再决定是否修改 |
| 保存和交付 | SQLite 持久化、画面与分镜结构独立撤销、刷新恢复、PNG/SVG 下载 |

试着输入：

> 给咖啡店拍一条15秒雨天促销短片，分3个镜头：女孩雨中进店、店员递咖啡、产品特写。女孩穿黄色雨衣，店员穿白衬衫绿围裙。最后写“雨天咖啡买一送一”。保存每镜景别和时长。

随后可以说“把第二个镜头移到最后”，或“检查递杯镜头中女孩是否握住杯柄，指出具体偏差”。这些是需求示例，Agent 通过模型原生工具调用决定执行方式，没有固定句式路由或预设分镜模板。

## 本地运行

准备 Python 3.11+、uv、Node.js 20+，以及可用的模型 API 密钥。当前验证模型为 `deepseek/deepseek-v4.1-flash`；语音和文字使用同一条 Agent 通路。画廊和管理按钮可离线使用，创作与看图评审需要模型服务。

终端一，从仓库根目录启动后端：

```powershell
cd backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 在 .env 中填入 VOICECANVAS_SHOT_LLM_API_KEY；已有 .env 时直接编辑，勿覆盖。
uv sync --frozen --no-editable
$env:PYTHONPATH="src"
uv run --frozen --no-editable uvicorn voicecanvas.api.main:app --host 127.0.0.1 --port 8000
```

终端二，从仓库根目录启动前端：

```powershell
cd frontend
npm run prototype
```

前端使用 Node 内置静态服务，这一步无需 `npm install`。打开 [首页](http://127.0.0.1:4178/index.html)，点击“开始我的创作”。后端健康检查为 [GET /health](http://127.0.0.1:8000/health)。可选看图工具需要服务端已安装 Edge/Chromium；具体配置、数据保存和 Docker 边界见[部署指南](docs/DEPLOYMENT.md)。

## 工程实现与能力边界

项目实现了工具调用执行与交付核对、SVG 白名单及原子源码修改、独立版本历史、并发冲突处理、任务持久化恢复，以及直接文字编辑的测量和保存闭环。领域与应用层通过协议隔离模型、浏览器、数据库和 HTTP。

画面构图、SVG 绘制、自然语言决策和图片评审来自外部 DeepSeek 模型；语音识别与播报来自浏览器 Web Speech API；内置作画知识改编自有明确许可的第三方 skill。这些能力不作为项目自研模型或自研语音识别来描述。来源和用途见[依赖与原创边界](docs/技术选型与依赖声明.md)。

真实验证中，完整三镜头需求能形成独立镜头并保存；单镜生成关闭思考后的两个样本约为16.7秒、20.8秒，不能视为平均延迟。递杯用例中，模型能够看出主要偏差，一次修正后仍未画准。当前没有证据证明已达到稳定成品画质，也没有正式客户使用数据。[验证索引](docs/experiments/README.md) 保留原始产物、用量和失败样本。

当前版本未提供账号权限、多人协作、视频生成或生产环境任务队列。服务使用单个 Uvicorn 进程；浏览器语音支持和字体效果需在实际设备上检查。

## 阅读与验证

| 想了解什么 | 文档 |
| --- | --- |
| 如何创作、改字、恢复和导出 | [使用指南](docs/使用指南.md) |
| 环境变量、网络、数据库、Docker | [部署指南](docs/DEPLOYMENT.md) |
| Agent 如何决策，状态如何保存 | [架构说明](docs/ARCHITECTURE.md) |
| 具体接口、参数和错误语义 | [API 说明](docs/API.md) |
| 如何运行回归和浏览器验收 | [测试指南](docs/TESTING.md) |
| 第三方能力、许可与自研范围 | [依赖与原创边界](docs/技术选型与依赖声明.md) |

基础回归分别从仓库根目录执行：

```powershell
cd backend
uv run --frozen --no-editable pytest -q
```

```powershell
cd frontend
npm test
```
