# 当前工作台 API

[项目首页](../README.md) · [架构说明](ARCHITECTURE.md) · [测试指南](TESTING.md)

后端默认 `http://127.0.0.1:8000`，请求体为 JSON。以下是自由 SVG 工作台使用的接口；完整类型和仍保留的历史接口可查看运行服务的 `/docs`。当前没有账号鉴权或项目权限隔离。

## 项目与分镜

| 方法与路径 | 输入或返回 |
| --- | --- |
| `POST /api/storyboards` | `{title?}`；创建含一个空镜头的项目 |
| `GET /api/storyboards` | 最近50个项目的 ID、标题与镜头数 |
| `GET /api/storyboards/{id}` | 顺序、共用设定、每镜说明/景别/时长/当前 SVG、结构版本、当前画面完整状态 |
| `POST /api/storyboards/{id}/manage` | `{expectedVersion, action, targetId?, title?, position?, count?, confirmed?}` |
| `POST /api/storyboards/{id}/import-svg` | `{expectedVersion, title, svg}`；校验自包含 SVG 后保存并返回分镜，201 |

管理 action 为 `add/switch/rename/rename_project/move/duplicate/delete/undo/redo`。位置从1开始；省略目标使用当前镜头。每项目1–40镜，单次新增1–12镜。复制只复制当前画面，副本建立独立历史。

结构版本与画面版本分别检查。切换不消耗结构历史，但增加项目版本。删除仅移除引用，可通过结构撤销恢复；至少保留一镜。项目结构与新增画面同事务保存，条件更新失败不会留下半个新增镜头。

导入沿用绘图 SVG 校验（1280×720、最大 1 MB），无需调用模型。导入记录在结构历史中，新增镜头拥有独立画面历史。

## 自主 Agent 任务

`POST /api/storyboards/{id}/agent/runs` 提交任务，202返回 `{run, board}`：

```json
{"expectedVersion":0,"request":"制作15秒3镜头咖啡广告，每镜保存景别和时长","defaultDrawingStyle":"暖色手绘，背景简洁"}
```

`GET /api/storyboards/{id}/agent/run` 查询最新任务和实际项目，同样返回 `{run, board}`，无任务时 `run` 为 null。

| 字段 | 含义 |
| --- | --- |
| `status` | `running/completed/needs_input/failed/interrupted` |
| `summary` | 真实结果与未完成项；完成不代表画质自动合格 |
| `steps` | 实际工具调用参数、状态、结果；新步骤结果含 `elapsedSeconds` |
| `usage` | 决策与专门评审累计用量；绘图用量在镜头修订记录中 |
| `pendingDelete` | 等待用户确认的镜头与结构版本 |
| `clientActions` | 待浏览器执行的文件下载；服务端返回不等于用户已经保存 |

同项目已有运行任务时拒绝重复提交。刷新只 GET，不重复 POST。服务重启标记中断，不自动重放模型请求。删除确认必须对应已持久化目标和版本；Agent 路径要求用户明确回复“确认删除”或“确定删除”，不能从模型参数中伪造授权。工具集合、并发和预算见[架构说明](ARCHITECTURE.md#agent-的自主性与执行边界)。

`defaultDrawingStyle` 可省略，最多 500 字，作为本次任务的新画面兜底描绘。优先级为本次明确要求、项目共用设定、默认画风。任务保存当时提交的值，浏览器清除默认项后，后续请求不再传送该值。

## 单镜头与文字

| 方法与路径 | 输入或行为 |
| --- | --- |
| `POST /api/shots` | `{title?}`；创建独立空镜头，正常 UI 由分镜创建接口统一编排 |
| `GET /api/shots/{id}` | SVG、文字块、版本、游标、可撤销/重做状态和历史元信息 |
| `POST /api/shots/{id}/generate` | `{expectedVersion,instruction}`；初稿或已有画面源码修改 |
| `POST /api/shots/{id}/text` | 确定性改字，无模型请求，输入示例见下 |
| `POST /api/shots/{id}/undo`、`redo` | `{expectedVersion}` |
| `GET /api/shots/{id}/export.svg` | 当前自包含 SVG；空白镜头409 |

文字保存示例：

```json
{"expectedVersion":1,"index":0,"lines":["第一行","第二行"],"fontSize":28,"lineHeight":1.35,"y":120}
```

`index` 来自当前状态的 `texts`，只对当前画面版本有效；组成行见 `indices`。`editable/reason` 说明是否能直接编辑。文本最多2000字、100行，字号8–160，行高倍数1–3，`y` 为 SVG 内部基线。前端负责实际字体测量和视觉提示，服务端负责受限重建与参数校验。

生成、文字保存和撤销重做返回完整当前画面状态。`revisions` 包含指令、时间、模型和用量，不重复返回所有历史 SVG。直接改字的 `model=null`、`usage={}`。PNG 由浏览器从当前 SVG 导出，没有服务端 PNG 导出接口。

## 版本绑定真实预览

`GET /api/storyboards/{boardId}/shots/{shotId}/previews/{imageId}.png` 返回工具已经生成的1280×720 PNG。

图片 ID 由 `render_shot` 或 `review_shot` 结果提供，绑定项目、镜头、版本、源码摘要和渲染器。GET 只读取当前版本的既有缓存，不启动渲染、不调用模型。返回 `image/png`、`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`；过期返回409，未配置视觉服务503。

`render_shot({shotId})` 和 `review_shot({shotId,focus?})` 是 Agent 工具，不是独立 POST 路由。前者给下一次决策真实图片，后者直接进行同模型图片评审。结果包含 `shotVersion/imageId/previewUrl`；专门评审另含原文和 `requiresUserAcceptance=true`。图片 Base64 不写入任务记录。

## 首页与错误

`GET /health` 返回服务状态。`GET /api/showcase?category=…` 返回分类和静态作品，`GET /api/showcase/{id}/artwork` 返回白名单 SVG；画廊展示与用户创作项目独立，不调用模型或素材桶。点击创作使用 `/api/storyboards`。

| 状态码 | 含义 |
| --- | --- |
| 404 | 目标不存在 |
| 409 | 版本冲突、已有运行任务或导出空白画面 |
| 422 | 无效参数、目标不属于项目或 SVG 校验未通过 |
| 502 | 单镜头直接生成的外部模型失败 |
| 503 | 预览服务未配置 |

Agent 内部工具错误通常记录为失败步骤，并交回模型决策；查询 API 仍可能是200，调用方要读取 `run.status` 与步骤结果。失败保留此前保存的画面，不自动重试付费生成。旧 `/command` 句式路由已删除，不作为兼容入口。
