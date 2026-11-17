"""任务记录是执行证据；不规定 Agent 必须按哪条作画流程行动。"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class AgentDecision(BaseModel):
    content: str = ""
    calls: list[AgentToolCall] = Field(default_factory=list, max_length=12)


class AgentStep(BaseModel):
    call: AgentToolCall
    status: Literal["running", "succeeded", "failed"] = "running"
    result: dict[str, Any] | None = None


class StoryboardAgentRun(BaseModel):
    id: str
    board_id: str = Field(alias="boardId")
    request: str
    status: Literal["running", "completed", "needs_input", "failed", "interrupted"] = "running"
    summary: str = "正在理解需求"
    steps: list[AgentStep] = Field(default_factory=list)
    client_actions: list[dict] = Field(default_factory=list, alias="clientActions")
    pending_delete: dict | None = Field(default=None, alias="pendingDelete")
    usage: dict[str, int] = Field(default_factory=dict)
    created_at: str = Field(alias="createdAt")
