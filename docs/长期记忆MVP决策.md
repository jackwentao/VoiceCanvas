# 长期记忆 MVP 决策

## 决策结论

VoiceCanvas 长期记忆以可显式管理的 MVP 形式落地，保存跨项目生效的用户偏好、命名习惯、布局习惯和工作流倾向。长期记忆只作为 AI Planner 的上下文建议，不直接覆盖当前项目状态，也不能绕过用户本轮指令、命令校验和命令执行链路。

## 范围

当前 MVP 包含：

- 长期记忆领域模型：记录类型、作用范围、置信度、状态、来源证据和最近使用时间。
- 仓储协议：应用层只依赖 `UserMemoryRepository`，不绑定具体存储介质。
- 本地 JSON 仓储：用于 MVP、离线演示和单元测试。
- 服务层：支持新增、修改、确认、拒绝、归档、删除和相关性检索。
- REST API：支持前端查看、新增、修改和删除长期记忆。
- 前端原型管理面板：用户可以在“设置 / 长期记忆”中显式管理长期记忆。
- 候选提取器：从明确用户表达中提取长期记忆候选，并过滤敏感信息。

当前 MVP 不包含：

- 真实 LLM 自动总结记忆。
- 向量数据库或云端同步。
- 自动把长期记忆注入现有 Planner 主链路。

这些能力应作为后续独立 PR 分步实现。

## 记忆类型

- `style_preference`：风格偏好，例如清爽绿色、留白较多、小红书风。
- `layout_preference`：布局偏好，例如标题放左上角、按钮放右下角。
- `naming_convention`：命名习惯，例如把第一镜头叫“主图”。
- `workflow_preference`：工作流偏好，例如带货分镜默认“主图、卖点、转化”三段结构。
- `negative_preference`：负向偏好，例如不喜欢太花、不用深色背景。

## 写入规则

- 明确长期表达，例如“以后都用”“默认”“记住”，可以生成高置信记忆。
- 单次软偏好，例如“这个风格不错”，只生成候选记忆，需要用户确认后再稳定复用。
- 密码、密钥、手机号、身份证、Token 等敏感信息默认不写入长期记忆。
- 低置信记忆不能静默污染用户体验，后续应通过右侧 AI 交互栏请求确认。

## 使用规则

- 当前用户指令优先于长期记忆。
- 当前项目状态优先于长期记忆。
- 长期记忆只用于补全用户未明确说明的风格、布局、命名和工作流倾向。
- 被拒绝或归档的记忆不参与上下文检索。

## 测试方式

```powershell
cd backend
uv run --no-editable pytest tests/test_user_memory_repository.py tests/test_user_memory_service.py tests/test_memory_extractor.py tests/test_user_memory_api.py
```

前端原型契约：

```powershell
cd frontend
npm test
```

完整后端回归：

```powershell
cd backend
uv run --no-editable pytest
```
