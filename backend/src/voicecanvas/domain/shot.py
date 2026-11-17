"""单镜头文档与版本；一次自然语言请求对应一个可撤销版本。"""

from pydantic import BaseModel, Field, model_validator


class ShotRevision(BaseModel):
    svg: str
    instruction: str
    created_at: str = Field(alias="createdAt")
    usage: dict[str, int] = Field(default_factory=dict)
    model: str | None = None


class ShotDocument(BaseModel):
    id: str
    title: str = "未命名镜头"
    version: int = Field(default=0, ge=0)
    revisions: list[ShotRevision] = Field(default_factory=list, max_length=40)
    cursor: int = -1

    @model_validator(mode="after")
    def valid_cursor(self) -> "ShotDocument":
        if not -1 <= self.cursor < len(self.revisions):
            raise ValueError("镜头版本位置无效")
        return self

    @property
    def svg(self) -> str | None:
        return self.revisions[self.cursor].svg if self.cursor >= 0 else None
