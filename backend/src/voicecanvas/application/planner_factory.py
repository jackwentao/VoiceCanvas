from voicecanvas.adapters.llm.openai_compatible import OpenAICompatibleLLMClient
from voicecanvas.application.command_planner import CommandPlanner
from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.llm_command_planner import LLMCommandPlanner
from voicecanvas.infrastructure.settings import LLMSettings


def create_planner_from_settings(settings: LLMSettings) -> CommandPlanner:
    """根据运行配置创建 Planner，默认保持本地 Demo 稳定可用。"""

    demo_planner = DemoCommandPlanner()
    if settings.planner == "demo":
        return demo_planner

    if not settings.base_url or not settings.model:
        return demo_planner

    client = OpenAICompatibleLLMClient(
        base_url=settings.base_url,
        model=settings.model,
        api_key=settings.api_key,
        provider=settings.provider,
    )
    fallback = demo_planner if settings.planner == "hybrid" else None
    return LLMCommandPlanner(
        client,
        fallback_planner=fallback,
        max_attempts=settings.max_attempts,
        timeout_seconds=settings.timeout_seconds,
        temperature=settings.temperature,
    )


def create_planner_from_env() -> CommandPlanner:
    return create_planner_from_settings(LLMSettings.from_env())
