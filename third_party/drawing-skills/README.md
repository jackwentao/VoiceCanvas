# 单镜头绘图技能来源

这里保存本次审阅和改编所依据的原始文档，未修改原文内容。每个来源的 `SOURCE.json` 记录固定 commit 和文件 SHA-256（按 Git 的 LF 换行规范化计算，便于跨平台核对），`LICENSE` 与原 README 保留授权和归属说明。应用不会执行这些文档中的脚本或命令，也不会将这些原文整体注入模型。

| 上游 skill | 来源与版本 | 采用内容 | 未接入部分 |
| --- | --- | --- | --- |
| SVG Creator | [upbrew-tech/svg-creator-skill](https://github.com/upbrew-tech/svg-creator-skill/tree/1eb83d602a992b69a1771c4e0116a9f7de6ffaa2)，Apache-2.0 | 前后景、光源与有色阴影、形体连接、滤镜范围 | 必须多轮看图的工作流、自动安装 CairoSVG 的脚本、动画、固定圆头线段人物方案 |
| Vector Illustration | [syi0808/svg-skills](https://github.com/syi0808/svg-skills/tree/c5937c2bed48aff98c12cda43ccba2ed6f2880f0)，MIT，Copyright (c) 2026 Yein Sung | 语义分组、曲线与接缝、负空间、局部修改保留无关内容 | scene.json 绑定、渲染/看图脚本、图像生成和其他 sibling skill 调用 |

项目改编后的运行文件为 `backend/src/voicecanvas/adapters/llm/skills/svg_illustration/SKILL.md`，分别提供 draw/edit 指令。该目录的 NOTICE 与两份许可证也随 Python 包发布；原始来源不是项目原创。应用新增的部分是按阶段加载、明确协议边界、配置开关和测试。

另检索了 [MengTo/Skills 的插画集合](https://github.com/MengTo/Skills/tree/main/agent-skills/illustration)。公开页面显示它包含明确风格的画布、配色、零件 kit 与渲染脚本；本次未导入，以免将任意镜头强行转为固定风格卡片。没有将搜索摘要当作已验证的运行效果。

`svg-creator` 的原文要求每张图完成渲染与视觉反馈循环；应用只改编其可用的作画知识，**没有实现完整上游 skill**。项目另行实现了由 Agent 自主选用的真实渲染与同模型评审工具，见[架构说明](../../docs/ARCHITECTURE.md#真实预览与评审)；加载技能本身不等于完成看图或保证人物质量。
