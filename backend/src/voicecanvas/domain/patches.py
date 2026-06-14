from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from voicecanvas.domain.project import CanvasElement, Scene


class PatchType(StrEnum):
    PROJECT_UPDATED = "PROJECT_UPDATED"
    SCENE_CREATED = "SCENE_CREATED"
    SCENE_UPDATED = "SCENE_UPDATED"
    SCENE_DELETED = "SCENE_DELETED"
    ACTIVE_SCENE_CHANGED = "ACTIVE_SCENE_CHANGED"
    ELEMENT_ADDED = "ELEMENT_ADDED"
    ELEMENT_UPDATED = "ELEMENT_UPDATED"
    ELEMENT_DELETED = "ELEMENT_DELETED"
    SCENE_CLEARED = "SCENE_CLEARED"


class CanvasPatch(BaseModel):
    id: str
    type: PatchType
    command_id: str = Field(alias="commandId")
    created_at: str = Field(alias="createdAt")
    scene_id: str | None = Field(default=None, alias="sceneId")
    element_id: str | None = Field(default=None, alias="elementId")
    scene: Scene | None = None
    element: CanvasElement | None = None
    patch: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
