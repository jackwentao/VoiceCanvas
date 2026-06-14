import os
from pathlib import Path
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


class AssetSettings(BaseModel):
    provider: Literal["local", "minio"] = "local"
    minio_endpoint: str | None = None
    minio_bucket: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_secure: bool = False
    public_base_url: str | None = None

    @classmethod
    def from_env(cls) -> "AssetSettings":
        load_dotenv()
        provider = cast(
            Literal["local", "minio"],
            os.getenv("VOICECANVAS_ASSET_PROVIDER", "local"),
        )
        return cls(
            provider=provider,
            minio_endpoint=os.getenv("VOICECANVAS_MINIO_ENDPOINT"),
            minio_bucket=os.getenv("VOICECANVAS_MINIO_BUCKET"),
            minio_access_key=os.getenv("VOICECANVAS_MINIO_ACCESS_KEY"),
            minio_secret_key=os.getenv("VOICECANVAS_MINIO_SECRET_KEY"),
            minio_secure=os.getenv("VOICECANVAS_MINIO_SECURE", "false").lower()
            in {"1", "true", "yes", "on"},
            public_base_url=os.getenv("VOICECANVAS_ASSET_PUBLIC_BASE_URL"),
        )


class StorageSettings(BaseModel):
    project_db_path: Path

    @classmethod
    def from_env(cls) -> "StorageSettings":
        load_dotenv()
        default_path = Path(__file__).resolve().parents[3] / "data" / "voicecanvas.sqlite3"
        return cls(
            project_db_path=Path(
                os.getenv("VOICECANVAS_PROJECT_DB_PATH", str(default_path))
            )
        )
