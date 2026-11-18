from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from voicecanvas.api.shots import create_shot_router
from voicecanvas.api.showcase import showcase_router
from voicecanvas.api.storyboard_agent import create_agent_router
from voicecanvas.api.storyboards import create_storyboard_router
from voicecanvas.infrastructure.shot_factory import (
    create_shot_service,
    create_storyboard_agent_service,
    create_storyboard_service,
)


def create_app() -> FastAPI:
    app = FastAPI(title="VoiceCanvas Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4178", "http://localhost:4178"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "voicecanvas-backend"}

    app.include_router(showcase_router())
    app.include_router(create_shot_router(create_shot_service))
    app.include_router(create_storyboard_router(create_storyboard_service))
    app.include_router(create_agent_router(create_storyboard_agent_service))
    return app


app = create_app()
