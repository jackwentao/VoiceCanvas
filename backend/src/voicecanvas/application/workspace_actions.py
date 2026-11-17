"""页面操作的固定契约。UI 不提交自由格式命令，也不参与业务决策。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class UIAction(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SwitchScene(UIAction):
    action: Literal["switch_scene"]
    scene_id: str = Field(alias="sceneId", min_length=1)


class SetBackground(UIAction):
    action: Literal["set_background"]
    scene_id: str = Field(alias="sceneId", min_length=1)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class RenameProject(UIAction):
    action: Literal["rename_project"]
    title: str = Field(min_length=1, max_length=120)


class ResetUsage(UIAction):
    action: Literal["reset_usage"]


class HistoryAction(UIAction):
    action: Literal["undo", "redo"]


WorkspaceAction = Annotated[
    SwitchScene | SetBackground | RenameProject | HistoryAction | ResetUsage,
    Field(discriminator="action"),
]
