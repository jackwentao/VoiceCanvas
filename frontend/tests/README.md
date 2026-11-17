# 前端测试

## 基础回归

```powershell
cd frontend
npm test
```

运行原型契约/语音回归、7 个首页控制器测试和 24 个自由分镜客户端/排版测试。移除旧工作台控制器后，同时删除其专属测试；历史 fixtures 仅用于回归，不会进入静态产品入口。

## 真实浏览器验收

```powershell
cd frontend
npm run test:workspace-browser
```

需要先启动静态前端和固定 SVG 生成器的后端 fixture，并设置已有 Playwright 与 Edge/Chromium 的路径。完整 PowerShell 命令见 [工作台适配](../../docs/main工作台分镜适配.md)。不自动下载安装工具，无在线模型调用。

覆盖首页 API 创建、分镜管理、直接改字、草稿保护、语音最终转写、删除确认、PNG 下载、刷新恢复和 390px 布局；同时确认旧 shot 页面返回 404，旧参数不会加载旧控制器或创建迁移项目。ASR/TTS 在适配器边界模拟，真实麦克风准确率需现场测试。
