"""镜头与分镜 Agent 的配置入口。"""

import os

from dotenv import load_dotenv

from voicecanvas.adapters.llm.svg_shot import OpenAICompatibleShotGenerator, ShotModelConfig
from voicecanvas.application.shot_service import ShotService
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.infrastructure.settings import shot_db_path
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository
from voicecanvas.infrastructure.sqlite_storyboard_repository import SQLiteStoryboardRepository


def create_storyboard_service() -> StoryboardService:
    return StoryboardService(SQLiteStoryboardRepository(shot_db_path()))


def create_shot_model_config() -> ShotModelConfig:
    load_dotenv()
    reasoning_effort = os.getenv("VOICECANVAS_SHOT_REASONING_EFFORT", "off").strip()
    config = ShotModelConfig(
        base_url=os.getenv("VOICECANVAS_SHOT_LLM_BASE_URL", ""),
        model=os.getenv("VOICECANVAS_SHOT_LLM_MODEL", ""),
        api_key=os.getenv("VOICECANVAS_SHOT_LLM_API_KEY", ""),
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
    repository = SQLiteShotRepository(shot_db_path())
    return ShotService(repository, OpenAICompatibleShotGenerator(config))


def create_storyboard_agent_service():
    from voicecanvas.adapters.llm.storyboard_agent import OpenAICompatibleStoryboardAgent
    from voicecanvas.adapters.rendering.chromium import ChromiumShotRenderer
    from voicecanvas.application.shot_visual_service import ShotVisualService
    from voicecanvas.application.storyboard_agent_service import StoryboardAgentService
    from voicecanvas.infrastructure.file_preview_store import FilePreviewStore
    from voicecanvas.infrastructure.sqlite_agent_run_repository import SQLiteAgentRunRepository

    shots = create_shot_service()
    boards = create_storyboard_service()
    agent = OpenAICompatibleStoryboardAgent(create_shot_model_config())
    root = shots.repository.db_path.parent / "shot-previews"
    return StoryboardAgentService(
        boards,
        shots,
        agent,
        SQLiteAgentRunRepository(shots.repository.db_path),
        ShotVisualService(
            boards, shots, ChromiumShotRenderer(root / "tmp"), FilePreviewStore(root)
        ),
        agent,
    )
