# VoiceCanvas 前端源码

手绘首页入口为 `prototype/index.html`，工作台入口为 `prototype/workspace.html`。
前端只负责展示与交互，项目、命令、澄清、历史、
用量和偏好均由后端决定与保存。

| 模块 | 边界 |
| --- | --- |
| `home.js`、`home-controller.js`、`home.css` | 画廊投影、分类请求、作品预览、创建请求和页面导航；不保存业务数据 |
| `app.js` | 页面装配、事件绑定、临时选中与面板状态 |
| `workspace-controller.js` | 请求串行化、快照读取、错误恢复；不运行领域命令 |
| `backend-client.js` | 固定业务接口和 SSE 传输 |
| `canvas-renderer.js`、`shape-renderer.js`、`text-layout.js` | 后端数据的画布投影 |
| `voice-session.js` | 麦克风、转写、播报与监听恢复 |
| `file-download.js` | 下载后端产物、后端授权的 PNG 展示转换 |
| `paper-theme.css` | 首页与工作台共用的纸张、墨绿、手写标题视觉令牌；原生 CSS，无新增依赖 |
| `workspace.css`、`canvas-elements.css` | 画桌界面与作品样式隔离；纸纹、胶带和涂鸦不进入作品导出 |

原型早期的 mock-data/state-sync/element-patch/export-service 已移到 `frontend/tests/fixtures`，
仅供历史回归测试使用，不随前端静态页面提供。新代码不得重新接入本地领域命令或浏览器业务存储。

```powershell
npm --prefix frontend run test:prototype
```

详见 [工作台接口](../../docs/工作台接口.md) 与 [使用验收](../../docs/工作台使用与验收.md)。

首页和工作台沿用同一套原创手绘视觉。字体使用系统字体栈，未下载字体或引入设计 SDK。
手写字体只用于界面标题；作品保留原有字体、真实比例和后端指定的颜色。
空白引导在窄屏预留最小高度，有作品时仍按后端画布比例缩放。
视觉验收步骤见上述使用验收文档的“首页与画桌视觉连续性”。
