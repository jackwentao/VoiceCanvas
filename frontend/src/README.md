# VoiceCanvas 前端源码

首页为 `prototype/index.html`，统一工作台为 `prototype/workspace.html`。工作台直接加载自由 SVG 分镜控制器，不提供旧页面、旧项目分流或单镜头迁移入口。

| 模块 | 边界 |
| --- | --- |
| home.js / home-controller.js | 画廊展示、创建分镜与页面导航 |
| showcase-client.js | 只读画廊请求 |
| svg-workspace.js | 页面装配、交互、语音指令与保存反馈 |
| storyboard-client.js | 分镜请求、结构版本、确认和并发控制 |
| shot-client.js | 画面生成、修改、直接改字与画面版本 |
| shot-text-editor.js / shot-text-layout.js | 文字测量、预览与排版 |
| shot-visual-feedback.js | 版本绑定的真实预览与评审记录 |
| voice-session.js | 麦克风、转写、播报与监听恢复 |
| paper-theme.css / workspace.css / svg-workspace.css | main 手绘视觉与自由 SVG 内容适配 |

业务状态保存在后端；浏览器本地记录最近项目定位，未应用的文字草稿仅保留在当前页面内存。模型 SVG 使用 Blob img 预览，不注入页面执行。

```powershell
npm --prefix frontend test
npm --prefix frontend run test:workspace-browser
```

浏览器测试需先启动后端 fixture，完整命令见 [测试指南](../../docs/TESTING.md#浏览器集成验收)。历史 fixtures 只供回归测试，不作为产品入口。
