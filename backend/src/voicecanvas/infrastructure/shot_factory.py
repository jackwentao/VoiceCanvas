"""单镜头配置入口；复用已有 LLM 配置，也允许独立覆盖。"""

import os
from pathlib import Path

from voicecanvas.adapters.llm.svg_shot import OpenAICompatibleShotGenerator, ShotModelConfig
from voicecanvas.application.shot_service import ShotService
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.infrastructure.settings import LLMSettings, StorageSettings
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository
from voicecanvas.infrastructure.sqlite_storyboard_repository import SQLiteStoryboardRepository


def create_storyboard_service() -> StoryboardService:
    default_path = StorageSettings.from_env().project_db_path.with_name("svg-shots.sqlite3")
    return StoryboardService(
        SQLiteStoryboardRepository(Path(os.getenv("VOICECANVAS_SHOT_DB_PATH", str(default_path))))
    )


def create_shot_model_config() -> ShotModelConfig:
    llm = LLMSettings.from_env()
    reasoning_effort = os.getenv("VOICECANVAS_SHOT_REASONING_EFFORT", "off").strip()
    config = ShotModelConfig(
        base_url=os.getenv("VOICECANVAS_SHOT_LLM_BASE_URL", llm.base_url or ""),
        model=os.getenv("VOICECANVAS_SHOT_LLM_MODEL", llm.model or ""),
        api_key=os.getenv("VOICECANVAS_SHOT_LLM_API_KEY", llm.api_key or ""),
        max_tokens=int(os.getenv("VOICECANVAS_SHOT_MAX_TOKENS", "32768")),
        timeout_seconds=float(os.getenv("VOICECANVAS_SHOT_TIMEOUT_SECONDS", "300")),
        drawing_skill=os.getenv("VOICECANVAS_SHOT_DRAWING_SKILL", "svg-illustration"),
        local_address=os.getenv("VOICECANVAS_SHOT_LOCAL_ADDRESS") or None,
        reasoning_effort=None if reasoning_effort == "provider-default" else reasoning_effort,
    )
    if not 1024 <= config.max_tokens <= 65536 or not 1 <= config.timeout_seconds <= 600:
        raise ValueError("单镜头输出预算应为 1024–65536，超时应为 1–600 秒")
    return config


def create_shot_service() -> ShotService:
    config = create_shot_model_config()
    default_path = StorageSettings.from_env().project_db_path.with_name("svg-shots.sqlite3")
    repository = SQLiteShotRepository(
        Path(os.getenv("VOICECANVAS_SHOT_DB_PATH", str(default_path)))
    )
    return ShotService(repository, OpenAICompatibleShotGenerator(config))


def create_storyboard_agent_service():
    from voicecanvas.adapters.llm.storyboard_agent import OpenAICompatibleStoryboardAgent
    from voicecanvas.application.storyboard_agent_service import StoryboardAgentService
    from voicecanvas.infrastructure.sqlite_agent_run_repository import SQLiteAgentRunRepository

    shots = create_shot_service()
    return StoryboardAgentService(
        create_storyboard_service(),
        shots,
        OpenAICompatibleStoryboardAgent(create_shot_model_config()),
        SQLiteAgentRunRepository(shots.repository.db_path),
    )
