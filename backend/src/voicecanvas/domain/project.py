from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, PositiveFloat, field_validator, model_validator


class ElementType(StrEnum):
    TEXT = "text"
    SHAPE = "shape"
    IMAGE = "image"
    CONNECTOR = "connector"
    UNKNOWN = "unknown"


class CanvasSpec(BaseModel):
    width: PositiveFloat = 1280
    height: PositiveFloat = 720
    background: dict[str, str] = Field(
        default_factory=lambda: {"type": "solid", "color": "#ffffff"}
    )


class CanvasElement(BaseModel):
    id: str
    type: ElementType
    x: float
    y: float
    width: PositiveFloat
    height: PositiveFloat
    z_index: int = Field(alias="zIndex")
    name: str | None = None
    text: str | None = None
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}

    @field_validator("x", "y")
    @classmethod
    def coordinate_must_be_finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("坐标必须是有限数字")
        return value


class Scene(BaseModel):
    id: str
    name: str
    order: int
    canvas: CanvasSpec = Field(default_factory=CanvasSpec)
    elements: list[CanvasElement] = Field(default_factory=list)
    description: str | None = None


class Project(BaseModel):
    id: str
    title: str
    mode: Literal["free_canvas", "storyboard"]
    scenes: list[Scene] = Field(min_length=1)
    active_scene_id: str = Field(alias="activeSceneId")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_scene_references(self) -> "Project":
        scene_ids = {scene.id for scene in self.scenes}
        if self.active_scene_id not in scene_ids:
            raise ValueError("activeSceneId 必须指向现有 Scene")

        orders = [scene.order for scene in self.scenes]
        if len(set(orders)) != len(orders):
            raise ValueError("Scene order 不能重复")

        return self
