import os
from typing import Literal, cast

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    planner: Literal["demo", "llm", "hybrid"] = "demo"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    provider: str = "openai-compatible"
    max_attempts: int = Field(default=3, ge=1)
    timeout_seconds: float = Field(default=20, gt=0)
    temperature: float = Field(default=0.1, ge=0, le=2)

    @classmethod
    def from_env(cls) -> "LLMSettings":
        load_dotenv()
        planner = cast(
            Literal["demo", "llm", "hybrid"],
            os.getenv("VOICECANVAS_PLANNER", "demo"),
        )
        return cls(
            planner=planner,
            base_url=os.getenv("VOICECANVAS_LLM_BASE_URL"),
            api_key=os.getenv("VOICECANVAS_LLM_API_KEY"),
            model=os.getenv("VOICECANVAS_LLM_MODEL"),
            provider=os.getenv("VOICECANVAS_LLM_PROVIDER", "openai-compatible"),
            max_attempts=int(os.getenv("VOICECANVAS_LLM_MAX_ATTEMPTS", "3")),
            timeout_seconds=float(os.getenv("VOICECANVAS_LLM_TIMEOUT_SECONDS", "20")),
            temperature=float(os.getenv("VOICECANVAS_LLM_TEMPERATURE", "0.1")),
        )
