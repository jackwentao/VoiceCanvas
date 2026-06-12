from fastapi import FastAPI

from voicecanvas.api.schemas import (
    HealthResponse,
    OrchestrationResponse,
    StartOrchestrationRequest,
)
from voicecanvas.graph.orchestration_graph import build_orchestration_graph


def create_app() -> FastAPI:
    app = FastAPI(title="VoiceCanvas Backend", version="0.1.0")
    orchestration_graph = build_orchestration_graph()

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="voicecanvas-backend")

    @app.post("/api/orchestrations", response_model=OrchestrationResponse)
    async def start_orchestration(request: StartOrchestrationRequest) -> OrchestrationResponse:
        result = orchestration_graph.invoke(
            {
                "project_id": request.project_id,
                "user_input": request.user_input,
                "events": [],
                "observations": [],
            }
        )

        return OrchestrationResponse(
            sessionId=result["session_id"],
            status=result["status"],
            stage=result["stage"],
            nextAction=result.get("next_action"),
            events=result.get("events", []),
            summary=result.get("summary"),
        )

    return app


app = create_app()
