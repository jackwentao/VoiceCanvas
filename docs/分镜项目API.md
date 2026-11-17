# 自由 SVG 分镜项目 API

在已有单镜头生成、文字编辑与版本 API 上增加项目编排。分镜领域只管理名称、顺序和稳定镜头 ID；每个画面继续由 `ShotService` 管理。管理操作不初始化绘图模型，也不要求模型密钥。

## 运行与接口

沿用根 README 的 FastAPI 启动命令与 `VOICECANVAS_SHOT_DB_PATH`。SQLite 在已有 `svg_shots` 旁自动创建 `svg_storyboards` 表，不修改旧版结构化项目表。

| 请求 | 用途 |
| --- | --- |
| `POST /api/storyboards` | `{title?}`，创建含一个空镜头的项目 |
| `GET /api/storyboards` | 最近更新的 50 个项目，返回 ID、标题和镜头数 |
| `GET /api/storyboards/{id}` | 顺序、当前镜头、缩略 SVG、画面版本、结构撤销状态和当前画面完整历史 |
| `POST /api/storyboards/{id}/manage` | `{expectedVersion, action, targetId?, title?, position?, count?, confirmed?}` |
| `POST /api/storyboards/{id}/agent/runs` | `{expectedVersion, request}`，提交自主工具调用任务 |
| `GET /api/storyboards/{id}/agent/run` | 最新持久化任务与实时项目 |

管理 action 为 `add / switch / rename / rename_project / move / duplicate / delete / undo / redo`。位置从 1 开始；省略目标时使用当前镜头。每个项目 1–40 镜头，每次新增 1–12 个。新增后选中第一个新增镜头；复制后选中副本。复制只复制当前画面并建立副本独立的初始版本。镜头名称属于项目元数据，不改写原画面标题。

自然语言由 Agent 按当前真实状态选择工具和执行顺序，不再通过固定句式路由。删除确认绑定稳定 ID 与版本，整组导出由浏览器实际下载。工具、预算、重启恢复和接口详见 [分镜 Agent](分镜Agent.md)。旧 `/command` 已移除。

## 持久化与并发

项目名称、顺序、新增、复制和删除共保留最近 100 个结构快照；切换当前镜头不占用结构历史，但会增加项目版本以防多个页面交错管理。`undo / redo` 恢复结构快照及其当时选中镜头，不回滚画面内容；画面继续使用原有独立历史。新增结构操作会截断当前结构重做分支。

删除只移除编排引用，保留画面文档，便于撤销恢复；本期没有物理清理或删除项目功能。超过结构历史窗口后，不能保证从界面恢复已删除镜头。管理版本与画面版本分开比较；错误为 404（不存在）、409（过期版本）、422（无效指令/参数）。版本冲突不自动重试模型。

SQLite 仓储在同一事务中提交项目更新和新增画面，CAS 失败不留下新增画面。工作台仅通过 `board` 定位项目，不提供单镜头迁移入口。

## 依赖边界与测试

复用已声明的 FastAPI/Pydantic、SQLite 和 Python 标准库，不新增包或服务。项目原创部分是分镜元数据、独立历史编排、Agent 工具协议、确认和版本协议；画面内容仍由外部模型生成。仓储通过 `StoryboardRepository` 端口隔离，领域与应用层不依赖 FastAPI、SQLite 或外部 SDK。

在 `backend` 执行：

```powershell
python -m pytest tests/test_storyboards.py -q
python -m pytest -q
```

测试使用临时 SQLite 和生成器替身，不需要联网或密钥，覆盖结构生命周期、独立画面历史、复制、删除恢复、冲突、事务；自主工具调用另见 test_storyboard_agent.py。语音与浏览器入口验收见 [语音分镜管理](语音分镜管理.md)。
