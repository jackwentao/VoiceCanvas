from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class StartOrchestrationRequest(BaseModel):
    project_id: str = Field(alias="projectId")
    user_input: str = Field(alias="userInput", min_length=1)

    model_config = {"populate_by_name": True}


class OrchestrationResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: Literal["RUNNING", "WAITING_FOR_USER", "COMPLETED", "FAILED", "CANCELLED"]
    stage: str
    next_action: dict[str, Any] | None = Field(default=None, alias="nextAction")
    events: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None

    model_config = {"populate_by_name": True}

