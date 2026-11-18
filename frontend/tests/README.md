# 前端测试

在本目录的上一级 `frontend` 执行 `npm test`，运行原型契约、首页控制器，以及分镜/画面/文字排版/视觉记录的 Node 回归。测试不请求在线模型，也不下载工具。

`npm run test:workspace-browser` 使用真实 API、临时 SQLite、固定生成器与决策替身；需要事先准备 Playwright 和 Edge/Chromium。完整启动命令、可配置路径和覆盖范围统一见[测试指南](../../docs/TESTING.md#浏览器集成验收)。

语音自动测试模拟 ASR/TTS 边界。真人识别准确率、真实模型决策与画质需使用实际设备和模型验收。
