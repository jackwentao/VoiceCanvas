"""兼容 Chat Completions 的工具调用适配器，不在应用层暴露 HTTP 或 SDK。"""

import json

import httpx

from voicecanvas.adapters.llm.svg_shot import ShotModelConfig
from voicecanvas.application.shot_service import ShotModelError
from voicecanvas.domain.storyboard_agent import AgentDecision, AgentToolCall


class OpenAICompatibleStoryboardAgent:
    def __init__(self, config: ShotModelConfig, transport: httpx.BaseTransport | None = None):
        self.config, self.transport = config, transport

    def decide(self, messages: list[dict], tools: list[dict]) -> tuple[AgentDecision, dict]:
        config = self.config
        if not config.base_url or not config.model:
            raise ShotModelError("请先配置后端绘图模型，再提交完整需求")
        payload = {
            "model": config.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        if config.reasoning_effort is not None:
            payload["reasoning_effort"] = config.reasoning_effort
        transport = self.transport
        if transport is None and config.local_address:
            transport = httpx.HTTPTransport(local_address=config.local_address)
        try:
            with httpx.Client(timeout=httpx.Timeout(90, connect=20), transport=transport) as c:
                response = c.post(
                    config.base_url.rstrip("/") + "/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer " + config.api_key},
                )
                if response.status_code >= 400:
                    raise ShotModelError(
                        f"任务 Agent 暂不可用（HTTP {response.status_code}），未自动重试"
                    )
                data = response.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") not in {"stop", "tool_calls"}:
                    raise ShotModelError("Agent 输出未完成，已保留当前分镜，请重新说明任务")
                message = choice["message"]
                calls = [
                    AgentToolCall(
                        id=call["id"],
                        name=call["function"]["name"],
                        arguments=json.loads(call["function"]["arguments"]),
                    )
                    for call in message.get("tool_calls") or []
                ]
                if len({call.id for call in calls}) != len(calls):
                    raise ValueError("重复工具 id")
                return AgentDecision(content=message.get("content") or "", calls=calls), {
                    k: v
                    for k, v in (data.get("usage") or {}).items()
                    if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and isinstance(v, int)
                    and v >= 0
                }
        except httpx.HTTPError as error:
            raise ShotModelError("任务 Agent 连接失败，当前分镜已保留") from error
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
            raise ShotModelError("Agent 工具调用格式无效，未执行本轮操作") from error
