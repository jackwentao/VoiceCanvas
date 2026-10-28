# VoiceCanvas 运行架构

[返回项目首页](../README.md)

## 前端架构

```mermaid
flowchart TD
    User["用户语音 / 点击 Demo 指令"]
    Voice["voice-session.js<br/>持续监听 / 噪声过滤 / 播报恢复"]
    App["app.js<br/>页面状态编排"]
    Client["backend-client.js<br/>HTTP / SSE / 降级"]
    State["state-sync.js<br/>Project State 归并"]
    Patch["element-patch.js<br/>CanvasPatch 应用"]
    Layout["text-layout.js<br/>文字自适应排版"]
    Catalog["render-catalog.json<br/>语义素材目录"]
    Canvas["主画布渲染"]
    History["左侧历史区"]
    AIPanel["右侧 AI 交互栏<br/>阶段 / 澄清 / 总结 / Token"]
    Export["export-service.js<br/>PNG / JSON 导出"]

    User --> Voice
    User --> App
    Voice --> App
    App --> Client
    Client --> State
    State --> Patch
    Patch --> Canvas
    Catalog --> Canvas
    Layout --> Canvas
    State --> History
    State --> AIPanel
    Canvas --> Export
```

前端只负责交互体验、画布投影、导出入口和降级展示；不持有后端可信业务规则。后端不可用时，前端会记录 `BACKEND_REQUEST_FAILED` 并回退到本地演示链路，保证比赛现场仍可展示基本流程。

## 后端架构

```mermaid
flowchart TD
    API["FastAPI<br/>HTTP / SSE 路由"]
    Service["OrchestrationService<br/>编排应用服务"]
    Planner["PlannerFactory<br/>Demo / LLM / Hybrid"]
    LLM["adapters/llm<br/>OpenAI-compatible"]
    Memory["UserMemoryService<br/>长期记忆检索与写入"]
    Resolver["ReferentResolver<br/>指代消解"]
    Validator["CommandValidator<br/>命令校验"]
    Executor["CommandExecutor<br/>确定性写操作"]
    Domain["domain<br/>Project / Scene / Element / Command"]
    History["HistoryManager<br/>撤销 / 重做 / 操作记录"]
    ProjectRepo["SQLiteProjectRepository<br/>Project State"]
    MemoryRepo["LocalUserMemoryRepository<br/>JSON 记忆"]
    Export["ExportService<br/>JSON / PNG 兜底导出"]
    Asset["AssetStorage<br/>Local / MinIO"]

    API --> Service
    Service --> Planner
    Planner --> LLM
    Service --> Memory
    Service --> Resolver
    Service --> Validator
    Validator --> Executor
    Executor --> Domain
    Executor --> History
    Service --> ProjectRepo
    Memory --> MemoryRepo
    Service --> Export
    API --> Asset
```

后端核心原则：

- AI 负责理解和规划，系统负责确定性执行。
- 所有画布写操作都经过 `CommandValidator` 和 `CommandExecutor`。
- Project State 是唯一可信状态，前端 CanvasPatch 只是 UI 增量投影。
- LLM、MinIO、未来七牛云能力都通过 adapter 接入，领域层不依赖外部 SDK。

## 数据完整流转

```mermaid
sequenceDiagram
    participant U as 用户
    participant F as 前端原型
    participant B as FastAPI
    participant O as OrchestrationService
    participant P as Demo/LLM Planner
    participant V as CommandValidator
    participant E as CommandExecutor
    participant R as SQLite Repository
    participant M as Memory Service
    participant A as MinIO/Local Asset

    U->>F: 语音输入或点击 Demo 指令
    F->>B: POST /api/orchestrations 或 /stream
    B->>O: 构造编排请求
    O->>M: 检索相关长期记忆
    O->>R: 读取当前 Project State
    O->>P: 生成结构化命令
    P-->>O: CanvasCommand 列表 / 澄清 / 总结
    O->>V: 校验命令字段、目标和风险
    V->>E: 提交合法命令
    E->>R: 写入 Project State 和 History
    E-->>O: 返回 CanvasPatch、History、Summary
    O-->>B: 返回响应或 SSE 事件
    B-->>F: project / patches / history / events / summary
    F->>F: 合并状态并刷新画布、历史区、AI 栏
    F->>B: GET /api/assets/catalog?path=...
    B->>A: 读取或代理素材
    A-->>B: 素材 URL 或二进制内容
    B-->>F: 可渲染素材地址
```

## 指令能力边界

完整指令验收基线见 [Demo 脚本与指令能力验收](./Demo脚本与指令能力验收.md)，预计实现、已完成、部分完成和未完成原因见 [指令完成情况](./指令完成情况.md)。

当前 README 只保留评审视角的边界：

- MVP 已覆盖创建分镜、镜头切换、文字/商品/标签/箭头添加、内容修改、视觉属性修改、位置调整、删除、澄清、撤销、重做、清空确认、JSON/PNG 导出、未知元素占位、长期记忆基础能力。
- 长图导出属于 P1，当前不作为 MVP 通过条件。
- 任意复杂图像生成质量、PS/Figma 级精细图层编辑、多人协作、无限步 AI 自动规划不在本次 MVP 承诺范围内。
- 普通编辑操作不依赖生图模型；未知对象会先落为结构化占位，保证创作链路不中断。
