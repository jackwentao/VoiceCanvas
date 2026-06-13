from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

LLMRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    role: LLMRole
    content: str


class LLMCompletion(BaseModel):
    content: str
    model: str | None = None
    provider: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class LLMClientError(RuntimeError):
    """LLM 调用错误，包含可展示给用户的错误类型。"""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class LLMClient(Protocol):
    """最小 LLM 客户端协议，便于替换供应商或注入测试假实现。"""

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float,
        timeout_seconds: float,
    ) -> LLMCompletion:
        ...
