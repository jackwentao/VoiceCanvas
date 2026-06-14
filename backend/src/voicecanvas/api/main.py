import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from voicecanvas.api.schemas import (
    CreateProjectRequest,
    CreateUserMemoryRequest,
    ExportProjectRequest,
    ExportProjectResponse,
    HealthResponse,
    ImportProjectRequest,
    OrchestrationResponse,
    ProjectStateResponse,
    ResumeOrchestrationRequest,
    StartOrchestrationRequest,
    UpdateUserMemoryRequest,
    UserMemoryListResponse,
    UserMemoryResponse,
)
from voicecanvas.application.export_service import ExportRequest
from voicecanvas.application.orchestration_service import (
    OrchestrationService,
    OrchestrationStreamChunk,
)
from voicecanvas.application.planner_factory import create_planner_from_env
from voicecanvas.application.user_memory_service import UserMemoryService
from voicecanvas.domain.user_memory import UserMemoryEvidence
from voicecanvas.infrastructure.local_user_memory_repository import LocalUserMemoryRepository


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


def _default_user_memory_service() -> UserMemoryService:
    path = Path(__file__).resolve().parents[3] / "data" / "user-memory.json"
    return UserMemoryService(LocalUserMemoryRepository(path))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_app(
    orchestration_service: OrchestrationService | None = None,
    user_memory_service: UserMemoryService | None = None,
) -> FastAPI:
    app = FastAPI(title="VoiceCanvas Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4178", "http://localhost:4178"],
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    memory_service = user_memory_service or _default_user_memory_service()
    service = orchestration_service or OrchestrationService(
        planner=create_planner_from_env(),
        user_memory_service=memory_service,
    )
    if orchestration_service is not None and user_memory_service is not None:
        service.set_user_memory_service(memory_service)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="voicecanvas-backend")

    @app.post("/api/orchestrations", response_model=OrchestrationResponse)
    async def start_orchestration(request: StartOrchestrationRequest) -> OrchestrationResponse:
        result = service.handle_user_input(
            request.project_id,
            request.user_input,
            user_id=request.user_id,
        )

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
        chunks = service.stream_user_input(
            request.project_id,
            request.user_input,
            user_id=request.user_id,
        )

        return StreamingResponse(
            _orchestration_sse_stream(chunks),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/projects", response_model=ProjectStateResponse)
    async def create_project(request: CreateProjectRequest) -> ProjectStateResponse:
        state = service.create_project(
            title=request.title,
            mode=request.mode,
            project_id=request.project_id,
        )

        return ProjectStateResponse(
            project=state.project.model_dump(by_alias=True),
            history=[entry.model_dump(by_alias=True) for entry in state.history],
            events=state.events,
        )

    @app.get("/api/projects/{project_id}", response_model=ProjectStateResponse)
    async def get_project(project_id: str) -> ProjectStateResponse:
        state = service.get_project_state(project_id)

        return ProjectStateResponse(
            project=state.project.model_dump(by_alias=True),
            history=[entry.model_dump(by_alias=True) for entry in state.history],
            events=state.events,
        )

    @app.post("/api/projects/{project_id}/export", response_model=ExportProjectResponse)
    async def export_project(
        project_id: str,
        request: ExportProjectRequest,
    ) -> ExportProjectResponse:
        try:
            result = service.export_project(
                project_id,
                ExportRequest.model_validate(request.model_dump(by_alias=True)),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return ExportProjectResponse(export=result.model_dump(by_alias=True))

    @app.post("/api/projects/import", response_model=ProjectStateResponse)
    async def import_project(request: ImportProjectRequest) -> ProjectStateResponse:
        try:
            state = service.import_project(request.payload)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return ProjectStateResponse(
            project=state.project.model_dump(by_alias=True),
            history=[entry.model_dump(by_alias=True) for entry in state.history],
            events=state.events,
        )

    @app.get("/api/users/{user_id}/memories", response_model=UserMemoryListResponse)
    async def list_user_memories(
        user_id: str,
        includeInactive: bool = False,
    ) -> UserMemoryListResponse:
        memories = memory_service.list_memories(user_id, include_inactive=includeInactive)
        return UserMemoryListResponse(memories=memories)

    @app.post("/api/users/{user_id}/memories", response_model=UserMemoryResponse)
    async def create_user_memory(
        user_id: str,
        request: CreateUserMemoryRequest,
    ) -> UserMemoryResponse:
        try:
            memory = memory_service.create_memory(
                user_id=user_id,
                kind=request.kind,
                content=request.content,
                scope=request.scope,
                confidence=1.0,
                status="active",
                evidence=[
                    UserMemoryEvidence(
                        source="explicit_user_statement",
                        createdAt=_now(),
                    )
                ],
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return UserMemoryResponse(memory=memory)

    @app.patch("/api/memories/{memory_id}", response_model=UserMemoryResponse)
    async def update_user_memory(
        memory_id: str,
        request: UpdateUserMemoryRequest,
    ) -> UserMemoryResponse:
        patch = request.model_dump(exclude_unset=True)
        try:
            memory = memory_service.update_memory(memory_id, **patch)
        except ValueError as error:
            if str(error) == "长期记忆不存在":
                raise HTTPException(status_code=404, detail=str(error)) from error
            raise HTTPException(status_code=400, detail=str(error)) from error
        return UserMemoryResponse(memory=memory)

    @app.delete("/api/memories/{memory_id}", status_code=204)
    async def delete_user_memory(memory_id: str) -> None:
        memory_service.delete(memory_id)

    return app


app = create_app()
