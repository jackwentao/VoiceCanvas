# 测试与验收

[项目首页](../README.md) · [部署指南](DEPLOYMENT.md) · [真实验证记录](experiments/README.md)

## 基础回归

每组从仓库根目录开始。配置好 Python 环境后运行：

```powershell
cd backend
uv sync --frozen --no-editable
uv run --frozen --no-editable pytest -q
uv run --frozen --no-editable ruff check .
uv run --frozen --no-editable mypy src
```

```powershell
cd frontend
npm test
```

前端测试用 Node 内置测试运行器和断言，无需安装 npm 包。默认测试不请求真实模型；旧 Planner 的在线用例默认跳过。测试数量会随实现变化，以本次运行输出为准，不以历史文档数字代替当前结果。

## 当前产品重点用例

在 `backend` 下可按关注点运行：

| 范围 | 命令 |
| --- | --- |
| SVG、修改协议、历史与冲突 | `python -m pytest tests/test_single_shot.py -q` |
| 分镜结构与自主工具调用 | `python -m pytest tests/test_storyboards.py tests/test_storyboard_agent.py -q` |
| 直接改字与真实文字样本回放 | `python -m pytest tests/test_shot_text_edit.py tests/test_storyboard_text_replay.py -q` |
| 真实图片协议、预览缓存、版本与评审预算 | `python -m pytest tests/test_shot_visual_tools.py -q` |
| 内置作画知识及首页画廊 | `python -m pytest tests/test_drawing_skills.py tests/test_showcase_api.py -q` |

回放样本位于 `docs/experiments/subject-quality-20261117` 和 `storyboard-text-20261117`，被后端测试读取，不能当作无用截图目录删除。替身验证协议、保存和错误边界；审美、动作和真实模型表现另看[实测记录](experiments/README.md)。

## 浏览器集成验收

需要已有 Playwright 与 Edge/Chromium。以下命令不自动下载或安装浏览器；只有已准备相关工具时才运行。使用独立测试数据库，固定 SVG 和决策替身，无在线模型请求。语音只模拟 ASR/TTS 边界，不能证明真人中文识别准确率。

终端一，从仓库根目录启动测试 API，目录可自行改到工作盘：

```powershell
cd backend
New-Item -ItemType Directory -Force D:/VoiceCanvas-test | Out-Null
$env:PYTHONPATH="src"
$env:VOICECANVAS_E2E_DATA_DIR="D:/VoiceCanvas-test"
uv run --frozen --no-editable uvicorn browser_fixture:app --app-dir tests --host 127.0.0.1 --port 8015
```

终端二，从仓库根目录启动静态前端：

```powershell
cd frontend
npm run prototype
```

终端三，从仓库根目录执行测试：

```powershell
cd frontend
# Playwright 不在当前模块解析路径时，指定其所在项目的 package.json 绝对路径。
# $env:VOICECANVAS_PLAYWRIGHT_PACKAGE="D:/Tools/browser-tests/package.json"
$env:VOICECANVAS_BROWSER_PATH="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
$env:VOICECANVAS_E2E_OUTPUT="D:/VoiceCanvas-test/screenshots"
npm run test:workspace-browser
```

将浏览器路径改为本机已安装位置；省略时使用 Playwright 已有浏览器。测试 API 默认8015、UI 默认4178，可用 `VOICECANVAS_E2E_API_URL` 与 `VOICECANVAS_E2E_UI_URL` 覆盖。8015只供测试，正常产品应使用8000。

脚本覆盖：首页创建项目、独立镜头、改字与草稿保护、复制排序、删除确认与撤销、模拟最终语音转写、刷新恢复、PNG 下载、390px布局以及旧入口移除。它不覆盖模型真实工具选择或全部视觉工具 UI，需要下列在线验收补充。

## 真实模型与现场验收

按[部署指南](DEPLOYMENT.md) 启动正常产品。以下操作会使用配置的模型额度：

1. 输入完整三镜头需求，检查列表确实有三个独立画面、景别和时长，不是一个 SVG 拼图。
2. 提出局部改画，确认实际变化和无关对象是否保留；撤销、重做、刷新后再次检查。
3. 直接改一句已有对白，确认即时预览、保存和导出一致，且没有生成模型请求。
4. 请求检查手与杯子的接触，展开真实 PNG 和评审原文；改画后确认旧评审标历史。
5. 管理排序后请求整组导出，检查浏览器实际收到全部文件；后端动作列表不等于下载成功。
6. 在真实设备授权麦克风，说需求、等待执行、继续下一条，再关闭麦克风。记录识别错误，不能用模拟转写替代。
7. 两个页面修改同一项目，旧版本应冲突并同步；服务重启后不应自动重放付费任务。

每次记录模型/端点、配置、原始请求、调用用量、实际耗时及全部输出，失败样本一并保留。区分“合法保存”“需求表达正确”和“画质可交付”；少量样本不外推稳定成功率或平均延迟。旧 `VOICECANVAS_RUN_REAL_LLM_TESTS` 用例测试历史 Planner，不作为当前分镜 Agent 的在线验收入口。
