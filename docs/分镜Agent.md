# 分镜 Agent

自然语言不再由正则决定动作。Chat Completions 工具调用模型看到当前真实镜头状态、用户需求与上一任务摘要，自主决定拆镜数量、工具、顺序和是否修改已有画面。没有固定的「规划→逐镜画图→自审」工作流。应用层循环只执行模型选择的工具、返回结果并限制预算。

## 能力与执行边界

- `create_shots` / `describe_shot`：创建镜头或修改描述、景别、时长；首次拆镜复用唯一空镜头。
- `set_context`：保存共同角色外观和画风，首次生成自动携带。
- `draw_shot`：自由 SVG 生成或修改；同轮不同镜头最多两镜并发，逐镜保存。
- `manage_storyboard` / `move_shot_history`：结构管理及单镜头画面撤销重做。
- `get_storyboard` / `inspect_shot`：真实数据和 SVG 源码查询，不能用源码检查冒充视觉验收。
- `render_shot` / `review_shot`：可选真实 PNG 渲染和同一模型图片评审。工具由 Agent 自主选择，缓存、版本和资源边界见 [镜头视觉工具](镜头视觉工具.md)。
- `delete_shot`：绑定目标与版本等待用户确认，模型无法通过工具参数自行确认。
- `export_shots`：返回浏览器下载请求；后台返回不代表文件已下载。
- `finish_task`：核对交付镜头存在、画面已保存、数量和总时长；语义与画质仍需用户验收。

服务端同时记录本轮实际创建/绘制的镜头，防止模型以空交付跳过已创建但未绘制的镜头。模型只拿到各工具能力，不规定它必须调用哪些；只要交付证据不满足就返回错误供它继续决策。在线原始记录和看图后的失败项见 [真实验收](experiments/storyboard-agent-20261117/README.md)。

每任务最多 16 次模型决策、40 个工具步骤、8 次绘图、每镜 2 次绘图。无隐式付费重试。预算限制是执行边界，不是创作模板。一个镜头失败时保留其他已完成结果，下一任务带入当前实际状态。任务与步骤保存在 SQLite `svg_agent_runs`，重启会标记中断，不自动重放结果未知的绘图。

目前运行单个 Uvicorn 进程，不能使用多 worker；任务线程归该进程管理。前端刷新通过 GET 查询同一任务，不重复 POST。进程中断后用户明确继续，Agent 根据已保存画面决定补做哪些镜头。

## API

`POST /api/storyboards/{boardId}/agent/runs`：`{"expectedVersion":0,"request":"创作15秒三镜头咖啡广告"}`，202 返回 `{run,board}`。

`GET /api/storyboards/{boardId}/agent/run`：返回最新任务与实时项目数据。状态为 `running/completed/needs_input/failed/interrupted`，`steps` 是真实工具调用证据，`clientActions` 为待浏览器执行的导出。空任务为 null。

## 配置、原创边界与验证

复用 `VOICECANVAS_SHOT_LLM_*`、`VOICECANVAS_SHOT_REASONING_EFFORT` 和本地网络地址配置。决策使用同一外部模型的原生 tools 能力；模型必须支持 Chat Completions function calling。未配置或不支持时明确失败，不降级到正则或伪造成功。无需新增 Python/Node 依赖。模型负责语义理解与生成；项目原创部分是工具协议、可信执行、交付校验、持久化恢复、前端集成。

从 backend 运行：

```powershell
uv run --no-editable pytest tests/test_storyboard_agent.py tests/test_storyboards.py tests/test_single_shot.py
uv run --no-editable ruff check src tests/test_storyboard_agent.py
```

离线测试通过可替换决策端口和绘图端口，配合真实 SQLite 验证工具顺序自由、并行绘图、独立镜头、交付校验、删除确认、重复任务拒绝和中断恢复。在线实测必须另行检查模型实际选择、真实数量、时长以及画面，不把测试替身当成创作能力证据。
