from typing import Any

import httpx

from voicecanvas.adapters.llm.base import LLMClientError, LLMCompletion, LLMMessage


class OpenAICompatibleLLMClient:
    """调用 OpenAI-compatible Chat Completions 接口。"""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        provider: str = "openai-compatible",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._provider = provider

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float,
        timeout_seconds: float,
    ) -> LLMCompletion:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise LLMClientError("timeout", "LLM 请求超时，请检查网络或稍后重试") from error
        except httpx.NetworkError as error:
            raise LLMClientError("network", "LLM 网络请求失败，请检查网络连接") from error
        except httpx.HTTPError as error:
            raise LLMClientError("network", f"LLM 请求失败：{error}") from error

        if response.status_code >= 400:
            raise self._error_from_response(response)

        try:
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMClientError(
                "bad_response",
                "LLM 响应结构不符合 Chat Completions 格式",
            ) from error

        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("bad_response", "LLM 返回了空内容")

        return LLMCompletion(
            content=content,
            model=body.get("model", self._model),
            provider=self._provider,
            raw=body if isinstance(body, dict) else {},
        )

    def _error_from_response(self, response: httpx.Response) -> LLMClientError:
        category = self._category_from_status(response.status_code)
        message = self._message_from_body(response)
        return LLMClientError(category, message)

    def _category_from_status(self, status_code: int) -> str:
        if status_code in {401, 403}:
            return "auth"
        if status_code == 402:
            return "quota"
        if status_code == 429:
            return "rate_limit"
        if status_code >= 500:
            return "server"
        return "bad_response"

    def _message_from_body(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return f"LLM 服务返回 HTTP {response.status_code}"

        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            raw_message = error.get("message")
            code = error.get("code") or error.get("type")
            if isinstance(raw_message, str) and raw_message.strip():
                if response.status_code in {402, 429}:
                    return f"LLM 额度或频率受限：{raw_message}"
                if response.status_code in {401, 403}:
                    return f"LLM 鉴权失败：{raw_message}"
                return f"LLM 服务错误：{raw_message}"
            if isinstance(code, str):
                return f"LLM 服务错误：{code}"

        return f"LLM 服务返回 HTTP {response.status_code}"
