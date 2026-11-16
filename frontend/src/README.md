# VoiceCanvas 前端源码

工作台入口为 `prototype/index.html`。前端只负责展示与交互，项目、命令、澄清、历史、
用量和偏好均由后端决定与保存。

| 模块 | 边界 |
| --- | --- |
| `app.js` | 页面装配、事件绑定、临时选中与面板状态 |
| `workspace-controller.js` | 请求串行化、快照读取、错误恢复；不运行领域命令 |
| `backend-client.js` | 固定业务接口和 SSE 传输 |
| `canvas-renderer.js`、`shape-renderer.js`、`text-layout.js` | 后端数据的画布投影 |
| `voice-session.js` | 麦克风、转写、播报与监听恢复 |
| `file-download.js` | 下载后端产物、后端授权的 PNG 展示转换 |
| `workspace.css`、`canvas-elements.css` | 工作台布局与画布元素样式 |

原型早期的 mock-data/state-sync/element-patch/export-service 已移到 `frontend/tests/fixtures`，
仅供历史回归测试使用，不随前端静态页面提供。新代码不得重新接入本地领域命令或浏览器业务存储。

```powershell
npm --prefix frontend run test:prototype
```

详见 [工作台接口](../../docs/工作台接口.md) 与 [使用验收](../../docs/工作台使用与验收.md)。
