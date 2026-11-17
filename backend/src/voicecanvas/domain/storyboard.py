"""自由绘制分镜的编排元数据，不包含绘图 SDK 或重复的 SVG 历史。"""

from pydantic import BaseModel, Field, model_validator


class StoryboardShot(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=100)


class StoryboardState(BaseModel):
    title: str = Field(default="未命名分镜", min_length=1, max_length=100)
    shots: list[StoryboardShot] = Field(min_length=1, max_length=40)
    active_id: str = Field(alias="activeId")

    @model_validator(mode="after")
    def valid_members(self) -> "StoryboardState":
        ids = [shot.id for shot in self.shots]
        if len(set(ids)) != len(ids) or self.active_id not in ids:
            raise ValueError("分镜引用重复或当前镜头不存在")
        return self


class Storyboard(BaseModel):
    id: str
    version: int = Field(default=0, ge=0)
    states: list[StoryboardState] = Field(min_length=1, max_length=100)
    cursor: int = 0
    active_id: str = Field(alias="activeId")

    @model_validator(mode="after")
    def valid_history(self) -> "Storyboard":
        if not 0 <= self.cursor < len(self.states):
            raise ValueError("分镜历史位置无效")
        if self.active_id not in {shot.id for shot in self.state.shots}:
            raise ValueError("当前镜头不属于此分镜")
        return self

    @property
    def state(self) -> StoryboardState:
        return self.states[self.cursor]
