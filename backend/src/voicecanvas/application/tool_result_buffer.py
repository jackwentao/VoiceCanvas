from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallSpec(BaseModel):
    id: str
    tool_name: str = Field(alias="toolName")
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class ToolCallResult(BaseModel):
    tool_call_id: str = Field(alias="toolCallId")
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        alias="createdAt",
    )

    model_config = {"populate_by_name": True}


class ParallelToolObservation(BaseModel):
    type: Literal["parallel_tool_results"] = "parallel_tool_results"
    batch_id: str = Field(alias="batchId")
    results: list[ToolCallResult]
    complete: bool

    model_config = {"populate_by_name": True}


class ParallelToolResultBuffer:
    """缓存并行工具结果，等全部完成后一次性回灌给 Orchestrator。"""

    def __init__(self, batch_id: str, calls: list[ToolCallSpec]) -> None:
        if not calls:
            raise ValueError("并行工具批次不能为空")
        self._batch_id = batch_id
        self._calls = {call.id: call for call in calls}
        self._results: dict[str, ToolCallResult] = {}

    @property
    def ready(self) -> bool:
        return set(self._results) == set(self._calls)

    def record_success(self, tool_call_id: str, result: dict[str, Any]) -> None:
        self._ensure_known_call(tool_call_id)
        self._results[tool_call_id] = ToolCallResult(
            toolCallId=tool_call_id,
            success=True,
            result=result,
        )

    def record_error(self, tool_call_id: str, error: str) -> None:
        self._ensure_known_call(tool_call_id)
        self._results[tool_call_id] = ToolCallResult(
            toolCallId=tool_call_id,
            success=False,
            error=error,
        )

    def observation_if_ready(self) -> ParallelToolObservation | None:
        if not self.ready:
            return None
        return ParallelToolObservation(
            batchId=self._batch_id,
            results=[self._results[call_id] for call_id in self._calls],
            complete=True,
        )

    def _ensure_known_call(self, tool_call_id: str) -> None:
        if tool_call_id not in self._calls:
            raise ValueError(f"未知工具调用：{tool_call_id}")
