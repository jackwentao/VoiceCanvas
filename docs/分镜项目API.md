# 自由 SVG 分镜项目 API

在已有单镜头生成、文字编辑与版本 API 上增加项目编排。分镜领域只管理名称、顺序和稳定镜头 ID；每个画面继续由 `ShotService` 管理。管理操作不初始化绘图模型，也不要求模型密钥。

## 运行与接口

沿用根 README 的 FastAPI 启动命令与 `VOICECANVAS_SHOT_DB_PATH`。SQLite 在已有 `svg_shots` 旁自动创建 `svg_storyboards` 表，不修改旧版结构化项目表。

| 请求 | 用途 |
| --- | --- |
| `POST /api/storyboards` | `{title?, existingShotId?}`，创建含一个镜头的项目；可复制旧镜头及其完整历史 |
| `GET /api/storyboards` | 最近更新的 50 个项目，返回 ID、标题和镜头数 |
| `GET /api/storyboards/{id}` | 顺序、当前镜头、缩略 SVG、画面版本、结构撤销状态和当前画面完整历史 |
| `POST /api/storyboards/{id}/manage` | `{expectedVersion, action, targetId?, title?, position?, count?, confirmed?}` |
| `POST /api/storyboards/{id}/command` | `{expectedVersion, transcript}`，路由一条完整中文编排指令或画面描述 |

管理 action 为 `add / switch / rename / rename_project / move / duplicate / delete / undo / redo`。位置从 1 开始；省略目标时使用当前镜头。每个项目 1–40 镜头，每次新增 1–12 个。新增后选中第一个新增镜头；复制后选中副本。复制只复制当前画面并建立副本独立的初始版本。镜头名称属于项目元数据，不改写原画面标题。

`command` 对完整匹配的管理语句执行确定性路由；不支持的管理复合句返回 422，请用户分开表达。画面描述返回 `action: draw`、`targetId` 和 `instruction`，由客户端调用原有 `/api/shots/{id}/generate`。例如“新建一个镜头，画便利店门口”先新增，再返回绘图任务；绘图失败仍保留新空镜头。它不是任意自然语言 Agent 编排器。

“删除第二个镜头”仅返回 `request_delete`，不删除。客户端需绑定待确认的项目 ID、镜头 ID 和版本；确认后以 `confirmed: true` 提交 manage 请求。服务端拒绝未确认删除与删除最后一个镜头。`confirm / cancel / list / new_project / export_png / export_svg / undo_shot / redo_shot` 返回客户端执行意图，不在此接口操作画面或本地下载。

## 持久化与并发

项目名称、顺序、新增、复制和删除共保留最近 100 个结构快照；切换当前镜头不占用结构历史，但会增加项目版本以防多个页面交错管理。`undo / redo` 恢复结构快照及其当时选中镜头，不回滚画面内容；画面继续使用原有独立历史。新增结构操作会截断当前结构重做分支。

删除只移除编排引用，保留画面文档，便于撤销恢复；本期没有物理清理或删除项目功能。超过结构历史窗口后，不能保证从界面恢复已删除镜头。管理版本与画面版本分开比较；错误为 404（不存在）、409（过期版本）、422（无效指令/参数）。版本冲突不自动重试模型。

SQLite 仓储在同一事务中提交项目更新和新增画面，CAS 失败不留下新增画面。旧 `shot` URL 迁入项目时复制原文档到新 ID，原 URL 保持独立。原有 `/api/shots` 与 `index.html` 路径继续可用。

## 依赖边界与测试

复用已声明的 FastAPI/Pydantic、SQLite 和 Python 标准库，不新增包或服务。项目原创部分是分镜元数据、独立历史编排、命令路由、确认和版本协议；画面内容仍由外部模型生成。仓储通过 `StoryboardRepository` 端口隔离，领域与应用层不依赖 FastAPI、SQLite 或外部 SDK。

在 `backend` 执行：

```powershell
python -m pytest tests/test_storyboards.py -q
python -m pytest -q
```

测试使用临时 SQLite 和生成器替身，不需要联网或密钥，覆盖结构生命周期、独立画面历史、复制/迁移、删除恢复、冲突、事务和转写路由。语音与浏览器入口验收见后续前端分镜管理接入。
