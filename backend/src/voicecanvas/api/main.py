import json
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from voicecanvas.api.schemas import (
    HealthResponse,
    OrchestrationResponse,
    ProjectStateResponse,
    ResumeOrchestrationRequest,
    StartOrchestrationRequest,
)
from voicecanvas.application.orchestration_service import (
    OrchestrationService,
    OrchestrationStreamChunk,
)
from voicecanvas.application.planner_factory import create_planner_from_env


def _sse_event(event_name: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


def _orchestration_sse_stream(chunks: Iterator[OrchestrationStreamChunk]) -> Iterator[str]:
    for chunk in chunks:
        if chunk.type == "EVENT" and chunk.event is not None:
            yield _sse_event("orchestration.event", chunk.event)
        if chunk.type == "RESULT" and chunk.response is not None:
            yield _sse_event(
                "orchestration.result",
                chunk.response.model_dump(by_alias=True),
            )


def create_app(orchestration_service: OrchestrationService | None = None) -> FastAPI:
    app = FastAPI(title="VoiceCanvas Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4178", "http://localhost:4178"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    service = orchestration_service or OrchestrationService(planner=create_planner_from_env())

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="voicecanvas-backend")

    @app.post("/api/orchestrations", response_model=OrchestrationResponse)
    async def start_orchestration(request: StartOrchestrationRequest) -> OrchestrationResponse:
        result = service.handle_user_input(request.project_id, request.user_input)

        return OrchestrationResponse(
            sessionId=result.session_id,
            status=result.status,
            stage=result.stage,
            nextAction=result.next_action,
            project=result.project.model_dump(by_alias=True),
            patches=[patch.model_dump(by_alias=True) for patch in result.patches],
            history=[entry.model_dump(by_alias=True) for entry in result.history],
            events=result.events,
            summary=result.summary.model_dump(by_alias=True),
        )

    @app.post("/api/orchestrations/{session_id}/resume", response_model=OrchestrationResponse)
    async def resume_orchestration(
        session_id: str, request: ResumeOrchestrationRequest
    ) -> OrchestrationResponse:
        result = service.resume_user_input(request.project_id, session_id, request.answer)

        return OrchestrationResponse(
            sessionId=result.session_id,
            status=result.status,
            stage=result.stage,
            nextAction=result.next_action,
            project=result.project.model_dump(by_alias=True),
            patches=[patch.model_dump(by_alias=True) for patch in result.patches],
            history=[entry.model_dump(by_alias=True) for entry in result.history],
            events=result.events,
            summary=result.summary.model_dump(by_alias=True),
        )

    @app.post("/api/orchestrations/stream")
    async def stream_orchestration(request: StartOrchestrationRequest) -> StreamingResponse:
        chunks = service.stream_user_input(request.project_id, request.user_input)

        return StreamingResponse(
            _orchestration_sse_stream(chunks),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/projects/{project_id}", response_model=ProjectStateResponse)
    async def get_project(project_id: str) -> ProjectStateResponse:
        state = service.get_project_state(project_id)

        return ProjectStateResponse(
            project=state.project.model_dump(by_alias=True),
            history=[entry.model_dump(by_alias=True) for entry in state.history],
            events=state.events,
        )

    return app


app = create_app()
