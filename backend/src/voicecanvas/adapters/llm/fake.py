from collections.abc import Iterable

from voicecanvas.adapters.llm.base import LLMClientError, LLMCompletion, LLMMessage


class FakeLLMClient:
    """测试用 LLM 客户端，按顺序返回内容或抛出错误。"""

    def __init__(self, responses: Iterable[str | LLMCompletion | LLMClientError]) -> None:
        self._responses = list(responses)
        self.calls: list[list[LLMMessage]] = []

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float,
        timeout_seconds: float,
    ) -> LLMCompletion:
        self.calls.append(messages)
        if not self._responses:
            raise LLMClientError("bad_response", "FakeLLMClient 没有更多响应")

        response = self._responses.pop(0)
        if isinstance(response, LLMClientError):
            raise response
        if isinstance(response, LLMCompletion):
            return response

        return LLMCompletion(content=response, model="fake-llm", provider="fake")
