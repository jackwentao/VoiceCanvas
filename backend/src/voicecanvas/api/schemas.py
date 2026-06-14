from typing import Any, Literal

from pydantic import BaseModel, Field

from voicecanvas.domain.user_memory import (
    UserMemory,
    UserMemoryKind,
    UserMemoryScope,
    UserMemoryStatus,
)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class StartOrchestrationRequest(BaseModel):
    project_id: str = Field(alias="projectId")
    user_input: str = Field(alias="userInput", min_length=1)

    model_config = {"populate_by_name": True}


class ResumeOrchestrationRequest(BaseModel):
    project_id: str = Field(alias="projectId")
    answer: str = Field(min_length=1)

    model_config = {"populate_by_name": True}


class OrchestrationResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: Literal["RUNNING", "WAITING_FOR_USER", "COMPLETED", "FAILED", "CANCELLED"]
    stage: str
    next_action: dict[str, Any] | None = Field(default=None, alias="nextAction")
    project: dict[str, Any] | None = None
    patches: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | str | None = None

    model_config = {"populate_by_name": True}


class ProjectStateResponse(BaseModel):
    project: dict[str, Any]
    history: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class CreateProjectRequest(BaseModel):
    """新建项目请求。未传项目 ID 时由后端生成。"""

    title: str | None = Field(default=None, min_length=1)
    mode: Literal["free_canvas", "storyboard"] = "storyboard"
    project_id: str | None = Field(default=None, alias="projectId", min_length=1)

    model_config = {"populate_by_name": True}


class ExportProjectRequest(BaseModel):
    """项目导出入口请求，和 LLM 生成的 EXPORT_PROJECT payload 保持一致。"""

    format: Literal["json", "png"] = "json"
    scope: Literal["project", "active_scene", "scene"] = "project"
    scene_id: str | None = Field(default=None, alias="sceneId")

    model_config = {"populate_by_name": True}


class ExportProjectResponse(BaseModel):
    """导出结果。content 由前端统一转成下载文件。"""

    export: dict[str, Any]

    model_config = {"populate_by_name": True}


class ImportProjectRequest(BaseModel):
    """载入项目包。payload 可传完整导出包，也可直接传 Project 对象。"""

    payload: dict[str, Any]

    model_config = {"populate_by_name": True}


class CreateUserMemoryRequest(BaseModel):
    """前端显式新增长期记忆的请求模型。"""

    kind: UserMemoryKind
    content: str = Field(min_length=1)
    scope: UserMemoryScope = "global"

    model_config = {"populate_by_name": True}


class UpdateUserMemoryRequest(BaseModel):
    """前端显式修改长期记忆的请求模型，只暴露可控字段。"""

    kind: UserMemoryKind | None = None
    content: str | None = Field(default=None, min_length=1)
    scope: UserMemoryScope | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: UserMemoryStatus | None = None

    model_config = {"populate_by_name": True}


class UserMemoryResponse(BaseModel):
    """单条长期记忆响应。"""

    memory: UserMemory

    model_config = {"populate_by_name": True}


class UserMemoryListResponse(BaseModel):
    """长期记忆列表响应。"""

    memories: list[UserMemory] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
