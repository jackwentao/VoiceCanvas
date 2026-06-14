from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommandType(StrEnum):
    UPDATE_PROJECT = "UPDATE_PROJECT"
    CREATE_SCENE = "CREATE_SCENE"
    UPDATE_SCENE = "UPDATE_SCENE"
    CLEAR_SCENE = "CLEAR_SCENE"
    DELETE_SCENE = "DELETE_SCENE"
    SWITCH_SCENE = "SWITCH_SCENE"
    ADD_ELEMENT = "ADD_ELEMENT"
    UPDATE_ELEMENT = "UPDATE_ELEMENT"
    DELETE_ELEMENT = "DELETE_ELEMENT"
    ARRANGE_LAYOUT = "ARRANGE_LAYOUT"
    EXPORT_PROJECT = "EXPORT_PROJECT"


class CanvasCommand(BaseModel):
    id: str
    type: CommandType
    source: Literal["ai", "tool", "user_ui", "system"]
    payload: dict[str, Any]
    reason: str | None = None
    created_at: str = Field(alias="createdAt")

    model_config = {"populate_by_name": True}

