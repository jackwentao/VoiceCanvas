# VoiceCanvas 测试指南

[返回项目首页](../README.md)

下面各组命令均从仓库根目录开始。真实 LLM 验收会调用配置的外部模型。

## 测试命令

前端契约测试：

```powershell
cd frontend
npm run test:prototype
```

后端全量测试和质量检查：

```powershell
cd backend
uv sync --no-editable
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable mypy src
```

重点链路测试：

```powershell
cd backend
uv run --no-editable pytest tests/test_orchestration_service.py tests/test_command_executor.py tests/test_command_validator.py
uv run --no-editable pytest tests/test_export_service.py tests/test_render_catalog.py tests/test_minio_catalog_seed.py
uv run --no-editable pytest tests/test_user_memory_repository.py tests/test_user_memory_service.py tests/test_memory_extractor.py tests/test_user_memory_api.py
```

真实 LLM 验收测试默认跳过；需要实际调用时显式开启：

```powershell
cd backend
$env:VOICECANVAS_RUN_REAL_LLM_TESTS="1"
$env:VOICECANVAS_LLM_BASE_URL="https://你的-openai-compatible-endpoint/v1"
$env:VOICECANVAS_LLM_MODEL="你的模型名"
$env:VOICECANVAS_LLM_API_KEY="你的 API Key"
uv run --no-editable pytest tests/test_real_llm_command_planner.py -s
```
