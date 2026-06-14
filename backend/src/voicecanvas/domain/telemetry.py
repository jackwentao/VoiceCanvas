from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """单轮 LLM Token 用量统计。"""

    prompt_tokens: int = Field(default=0, alias="promptTokens", ge=0)
    completion_tokens: int = Field(default=0, alias="completionTokens", ge=0)
    total_tokens: int = Field(default=0, alias="totalTokens", ge=0)

    model_config = {"populate_by_name": True}

    def plus(self, other: "TokenUsage | None") -> "TokenUsage":
        if other is None:
            return self
        return TokenUsage(
            promptTokens=self.prompt_tokens + other.prompt_tokens,
            completionTokens=self.completion_tokens + other.completion_tokens,
            totalTokens=self.total_tokens + other.total_tokens,
        )

    @classmethod
    def from_openai_usage(cls, usage: object) -> "TokenUsage | None":
        if not isinstance(usage, dict):
            return None

        prompt_tokens = cls._non_negative_int(usage.get("prompt_tokens"))
        completion_tokens = cls._non_negative_int(usage.get("completion_tokens"))
        total_tokens = cls._non_negative_int(usage.get("total_tokens"))
        if prompt_tokens == 0 and completion_tokens == 0 and total_tokens == 0:
            return None

        return cls(
            promptTokens=prompt_tokens,
            completionTokens=completion_tokens,
            totalTokens=total_tokens or prompt_tokens + completion_tokens,
        )

    @staticmethod
    def _non_negative_int(value: object) -> int:
        if not isinstance(value, int):
            return 0
        return max(0, value)
