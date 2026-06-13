from typing import Literal

from pydantic import BaseModel, Field


class ElementMemory(BaseModel):
    """用于近期指代解析的轻量元素焦点。"""

    scene_id: str = Field(alias="sceneId")
    element_id: str = Field(alias="elementId")
    type: str
    name: str | None = None
    text: str | None = None
    aliases: list[str] = Field(default_factory=list)
    bounds: dict[str, float] = Field(default_factory=dict)
    source: Literal[
        "element_added",
        "element_updated",
        "element_deleted",
        "scene_created",
        "scene_cleared",
    ]
    last_touched_at: str = Field(alias="lastTouchedAt")

    model_config = {"populate_by_name": True}


class ConversationTurnMemory(BaseModel):
    """保留最近若干轮对话摘要，避免把完整历史塞给模型。"""

    id: str
    user_input: str = Field(alias="userInput")
    assistant_message: str = Field(alias="assistantMessage")
    action: str
    command_count: int = Field(alias="commandCount")
    focused_element_ids: list[str] = Field(default_factory=list, alias="focusedElementIds")
    created_at: str = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class ConversationMemorySnapshot(BaseModel):
    """Planner 每轮可读取的短期记忆快照。"""

    recent_turns: list[ConversationTurnMemory] = Field(default_factory=list, alias="recentTurns")
    focus_stack: list[ElementMemory] = Field(default_factory=list, alias="focusStack")

    model_config = {"populate_by_name": True}
