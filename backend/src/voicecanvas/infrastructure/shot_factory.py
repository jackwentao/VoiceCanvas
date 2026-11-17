"""单镜头配置入口；复用已有 LLM 配置，也允许独立覆盖。"""

import os
from pathlib import Path

from voicecanvas.adapters.llm.svg_shot import OpenAICompatibleShotGenerator, ShotModelConfig
from voicecanvas.application.shot_service import ShotService
from voicecanvas.infrastructure.settings import LLMSettings, StorageSettings
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository


def create_shot_service() -> ShotService:
    llm = LLMSettings.from_env()
    default_path = StorageSettings.from_env().project_db_path.with_name("svg-shots.sqlite3")
    repository = SQLiteShotRepository(
        Path(os.getenv("VOICECANVAS_SHOT_DB_PATH", str(default_path)))
    )
    config = ShotModelConfig(
        base_url=os.getenv("VOICECANVAS_SHOT_LLM_BASE_URL", llm.base_url or ""),
        model=os.getenv("VOICECANVAS_SHOT_LLM_MODEL", llm.model or ""),
        api_key=os.getenv("VOICECANVAS_SHOT_LLM_API_KEY", llm.api_key or ""),
        max_tokens=int(os.getenv("VOICECANVAS_SHOT_MAX_TOKENS", "32768")),
        timeout_seconds=float(os.getenv("VOICECANVAS_SHOT_TIMEOUT_SECONDS", "300")),
        drawing_skill=os.getenv("VOICECANVAS_SHOT_DRAWING_SKILL", "svg-illustration"),
    )
    if not 1024 <= config.max_tokens <= 65536 or not 1 <= config.timeout_seconds <= 600:
        raise ValueError("单镜头输出预算应为 1024–65536，超时应为 1–600 秒")
    return ShotService(repository, OpenAICompatibleShotGenerator(config))
