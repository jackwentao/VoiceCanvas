from typing import Literal

from pydantic import BaseModel, Field

UserMemoryKind = Literal[
    "style_preference",
    "layout_preference",
    "naming_convention",
    "workflow_preference",
    "negative_preference",
]
UserMemoryScope = Literal["global", "canvas", "storyboard", "commerce"]
UserMemoryStatus = Literal["candidate", "active", "rejected", "archived"]
UserMemoryEvidenceSource = Literal[
    "explicit_user_statement",
    "repeated_behavior",
    "assistant_suggestion",
]


class UserMemoryEvidence(BaseModel):
    """记录长期记忆的来源，便于用户回看、撤销和调试。"""

    source: UserMemoryEvidenceSource
    project_id: str | None = Field(default=None, alias="projectId")
    user_input: str | None = Field(default=None, alias="userInput")
    assistant_message: str | None = Field(default=None, alias="assistantMessage")
    created_at: str = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class UserMemory(BaseModel):
    """跨项目生效的用户长期记忆。"""

    id: str
    user_id: str = Field(alias="userId")
    kind: UserMemoryKind
    content: str = Field(min_length=1)
    scope: UserMemoryScope = "global"
    confidence: float = Field(ge=0, le=1)
    status: UserMemoryStatus = "candidate"
    evidence: list[UserMemoryEvidence] = Field(default_factory=list)
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    last_used_at: str | None = Field(default=None, alias="lastUsedAt")

    model_config = {"populate_by_name": True}


class UserMemoryContext(BaseModel):
    """Planner 每轮可读取的长期记忆快照。"""

    relevant: list[UserMemory] = Field(default_factory=list)
    usage_policy: str = Field(
        default="长期记忆只作为建议；当前用户指令、当前项目状态和用户澄清优先。",
        alias="usagePolicy",
    )

    model_config = {"populate_by_name": True}
