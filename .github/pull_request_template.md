## 标题

一句话说明本 PR 新增或修改了什么。

## 功能描述

说明该功能的作用、使用方式和用户能看到的变化。

## 实现思路

简要说明技术选型、核心实现逻辑和模块边界。

## 依赖与原创声明

- [ ] 本 PR 未新增第三方库、框架、SDK 或外部服务。
- [ ] 如新增或调整第三方依赖，已同步更新 `README.md` 和 `docs/技术选型与依赖声明.md`。
- [ ] 已说明第三方能力的使用边界、降级方案和测试方式。
- [ ] 已说明本 PR 中的原创功能部分。

## 测试方式

列出实际运行过的命令和结果，例如：

```powershell
cd backend
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

```powershell
cd frontend
npm run test:prototype
```

## PR 范围检查

- [ ] 本 PR 只做一件事。
- [ ] 大功能已拆分为更小的独立 PR。
- [ ] 合并后主分支仍可按 README 运行和复现演示效果。
- [ ] 相关文档、README、测试手段已同步更新。
