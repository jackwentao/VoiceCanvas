import pytest

from voicecanvas.application.tool_result_buffer import (
    ParallelToolResultBuffer,
    ToolCallSpec,
)


def test_parallel_tool_buffer_waits_until_all_results_are_ready() -> None:
    buffer = ParallelToolResultBuffer(
        "batch_1",
        [
            ToolCallSpec(id="call_scene", toolName="listScenes"),
            ToolCallSpec(id="call_elements", toolName="listElements"),
        ],
    )

    buffer.record_success("call_scene", {"scenes": ["scene_1"]})

    assert not buffer.ready
    assert buffer.observation_if_ready() is None

    buffer.record_success("call_elements", {"elements": ["el_1"]})
    observation = buffer.observation_if_ready()

    assert observation is not None
    assert observation.complete
    assert [result.tool_call_id for result in observation.results] == [
        "call_scene",
        "call_elements",
    ]


def test_parallel_tool_buffer_can_aggregate_success_and_error_together() -> None:
    buffer = ParallelToolResultBuffer(
        "batch_1",
        [
            ToolCallSpec(id="call_a", toolName="toolA"),
            ToolCallSpec(id="call_b", toolName="toolB"),
        ],
    )

    buffer.record_success("call_a", {"ok": True})
    buffer.record_error("call_b", "工具失败")

    observation = buffer.observation_if_ready()

    assert observation is not None
    assert observation.results[0].success
    assert not observation.results[1].success
    assert observation.results[1].error == "工具失败"


def test_parallel_tool_buffer_rejects_unknown_tool_call() -> None:
    buffer = ParallelToolResultBuffer(
        "batch_1",
        [ToolCallSpec(id="call_a", toolName="toolA")],
    )

    with pytest.raises(ValueError, match="未知工具调用"):
        buffer.record_success("call_missing", {})
