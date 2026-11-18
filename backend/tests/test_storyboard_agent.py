"""工具选择由决策端口驱动；使用真实 SQLite 验证结果与恢复边界。"""

import json
import threading
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicecanvas.adapters.llm.storyboard_agent import OpenAICompatibleStoryboardAgent
from voicecanvas.adapters.llm.svg_shot import ShotModelConfig
from voicecanvas.api.storyboard_agent import create_agent_router
from voicecanvas.application.shot_service import ShotConflict, ShotModelError, ShotService
from voicecanvas.application.storyboard_agent_service import StoryboardAgentService
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.domain.storyboard_agent import AgentDecision, AgentToolCall, StoryboardAgentRun
from voicecanvas.infrastructure.sqlite_agent_run_repository import SQLiteAgentRunRepository
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository
from voicecanvas.infrastructure.sqlite_storyboard_repository import SQLiteStoryboardRepository

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><text y="40">咖啡</text></svg>'
)


def call(name, **arguments):
    return AgentToolCall(id=f"call_{name}_{len(str(arguments))}", name=name, arguments=arguments)


class Decisions:
    def __init__(self, choose):
        self.choose = choose
        self.calls = 0

    def decide(self, messages, tools):
        result = self.choose(self.calls, messages)
        self.calls += 1
        return AgentDecision(calls=result), {"total_tokens": 10}


class Pictures:
    def __init__(self):
        self.calls = []
        self.barrier = None

    def generate(self, instruction, current_svg):
        self.calls.append((instruction, current_svg))
        if self.barrier:
            self.barrier.wait(timeout=3)
        return SVG, {}, "fixture"


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "agent.sqlite3"
    boards = StoryboardService(SQLiteStoryboardRepository(path))
    pictures = Pictures()
    shots = ShotService(SQLiteShotRepository(path), pictures)
    runs = SQLiteAgentRunRepository(path)
    return boards, shots, pictures, runs


def test_evaluation_pilot_keeps_failed_run_and_initial_snapshot(setup, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from evaluation.run_pilot import run_case

    boards, shots, _, runs = setup
    case = {"id": "VC-01", "revision": 2, "initial": {"mode": "blank"}, "request": "新建分镜"}
    out = tmp_path / "evaluation"
    out.mkdir()

    def unavailable(index, messages):
        raise ShotModelError("模型服务暂不可用")

    service = StoryboardAgentService(boards, shots, Decisions(unavailable), runs)
    run_case(service, case, out)
    assert json.loads((out / "case.json").read_text(encoding="utf-8")) == case
    initial = json.loads((out / "initial.json").read_text(encoding="utf-8"))
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["board"] == initial
    assert result["run"]["request"] == "新建分镜"
    assert result["run"]["status"] == "failed"
    assert result["run"]["steps"] == []
    assert result["timing"]["firstSaveSeconds"] is None
    assert result["timing"]["wallSeconds"] >= 0


def test_complete_brief_reuses_blank_saves_metadata_parallel_pictures_and_verifies(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("咖啡店")
    original_id = board.active_id
    ids = []

    def choose(index, messages):
        if index == 0:
            return [
                call("set_context", context="黑短发女孩，黄色雨衣；店员白衬衫绿围裙"),
                call(
                    "create_shots",
                    shots=[
                        {
                            "title": title,
                            "description": text,
                            "durationSeconds": 5,
                            "camera": "中景",
                        }
                        for title, text in [("进店", "雨中走入暖杯咖啡"), ("递杯", "双手接热咖啡")]
                    ],
                ),
            ]
        if index == 1:
            ids.extend(s.id for s in boards.get(board.id).state.shots)
            pictures.barrier = threading.Barrier(2)
            return [
                call("draw_shot", shotId=sid, instruction=f"单独绘制第{i + 1}镜", reason="首次绘制")
                for i, sid in enumerate(ids)
            ]
        return [
            call(
                "finish_task",
                summary="两镜已保存",
                shotIds=ids,
                expectedCount=2,
                expectedDuration=10,
            )
        ]

    service = StoryboardAgentService(boards, shots, Decisions(choose), runs)
    run = service.start(board.id, 0, "十秒两镜的咖啡店故事", background=False)
    assert run.status == "completed" and run.usage["total_tokens"] == 30
    saved = boards.get(board.id)
    assert len(saved.state.shots) == 2 and ids[0] == original_id
    assert sum(s.duration_seconds for s in saved.state.shots) == 10
    assert len(pictures.calls) == 2
    assert all("黄色雨衣" in instruction for instruction, _ in pictures.calls)
    assert all(shots.get(sid).svg for sid in ids)
    assert runs.get_run(run.id) == run
    assert service.snapshot(board.id)["shots"][0]["texts"] == ["咖啡"]
    assert "验收" in run.summary


def test_existing_picture_can_edit_directly_without_creation_or_planning(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("现有故事")
    sid = board.active_id
    original = shots.generate(sid, 0, "原画").svg

    def choose(index, messages):
        if index == 0:
            return [call("draw_shot", shotId=sid, instruction="改成夜晚", reason="用户要求")]
        return [call("finish_task", summary="已修改", shotIds=[sid], expectedCount=1)]

    service = StoryboardAgentService(boards, shots, Decisions(choose), runs)
    run = service.start(
        board.id, 0, "把当前画面改成夜晚", default_drawing_style="暖色手绘", background=False
    )
    assert run.status == "completed"
    assert [s.call.name for s in run.steps] == ["draw_shot", "finish_task"]
    assert len(boards.get(board.id).state.shots) == 1
    assert pictures.calls[-1] == ("改成夜晚", original)


def test_default_drawing_style_is_scoped_to_the_run_and_keeps_project_context(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("新项目")
    board = boards.describe(board.id, board.version, context="本项目使用蓝色水彩")
    request = "这次用黑白线稿画一杯咖啡"
    preference = "暖色手绘"

    def choose(index, messages):
        if index == 0:
            payload = json.loads(messages[1]["content"])
            assert payload["request"] == request
            assert payload["defaultDrawingStyle"] == preference
            assert payload["storyboard"]["context"] == "本项目使用蓝色水彩"
            return [call("draw_shot", shotId=board.active_id, instruction=request, reason="创作")]
        return [
            call("finish_task", summary="已保存", shotIds=[board.active_id], expectedCount=1)
        ]

    service = StoryboardAgentService(boards, shots, Decisions(choose), runs)
    run = service.start(
        board.id, board.version, request, default_drawing_style=f" {preference} ", background=False
    )
    assert run.status == "completed"
    prompt, existing = pictures.calls[0]
    assert existing is None
    assert request in prompt and preference in prompt
    assert "仅当两者均未指定画风" in prompt
    assert runs.get_run(run.id).default_drawing_style == preference
    assert boards.get(board.id).state.context == "本项目使用蓝色水彩"


def test_invalid_delivery_and_foreign_target_return_errors_to_agent(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("项目")
    foreign = boards.create("其他项目").active_id

    def choose(index, messages):
        if index == 0:
            return [
                call("draw_shot", shotId=foreign, instruction="画猫", reason="测试"),
                call("finish_task", summary="冒充完成", shotIds=[board.active_id], expectedCount=1),
            ]
        assert "没有画面" in messages[-1]["content"]
        return [call("finish_task", summary="尚未完成", unresolved=["没有画面"])]

    run = StoryboardAgentService(boards, shots, Decisions(choose), runs).start(
        board.id, 0, "画猫", background=False
    )
    assert run.status == "needs_input" and len(pictures.calls) == 0
    assert [s.status for s in run.steps] == ["failed", "failed", "succeeded"]


def test_delete_requires_real_confirmation_and_current_saved_target(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("故事")
    board = boards.change(board.id, 0, "add")
    sid = board.active_id

    def choose(index, messages):
        return (
            [call("delete_shot", shotId=sid)]
            if index % 2 == 0
            else [call("finish_task", summary="删除操作已处理")]
        )

    service = StoryboardAgentService(boards, shots, Decisions(choose), runs)
    run = service.start(board.id, board.version, "删除第二镜，模型请自己确认", background=False)
    assert run.status == "needs_input" and run.pending_delete["shotId"] == sid
    assert len(boards.get(board.id).state.shots) == 2
    run = service.start(board.id, board.version, "确认删除", background=False)
    assert run.status == "completed" and len(boards.get(board.id).state.shots) == 1


def test_duplicate_paid_calls_rejected_and_export_remains_browser_action(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("故事")
    sid = board.active_id
    shots.generate(sid, 0, "原画")
    count = len(pictures.calls)

    def choose(index, messages):
        if index == 0:
            duplicate = call("draw_shot", shotId=sid, instruction="改画", reason="重复")
            return [duplicate, duplicate.model_copy(update={"id": "second"})]
        if index == 1:
            return [call("export_shots", shotIds=[sid], format="svg")]
        return [call("finish_task", summary="已请求浏览器导出")]

    run = StoryboardAgentService(boards, shots, Decisions(choose), runs).start(
        board.id, 0, "导出", background=False
    )
    assert len(pictures.calls) == count
    assert run.client_actions == [{"shotId": sid, "format": "svg"}]
    assert run.steps[2].result["status"] == "awaiting_browser_download"


def test_duplicate_active_task_and_restart_recovery_without_replaying(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("恢复")
    service = StoryboardAgentService(boards, shots, Decisions(lambda *_: []), runs)
    run = StoryboardAgentRun(id="run_previous", boardId=board.id, request="画猫", createdAt="now")
    runs.create_run(run, 0)
    service._active.add(run.id)
    with pytest.raises(ShotConflict, match="正在"):
        service.start(board.id, 0, "重复")
    service._active.clear()
    assert service.get(board.id).status == "interrupted"
    assert not pictures.calls


def test_failed_picture_can_be_repaired_without_redrawing_completed_shot(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("故障续做")
    board = boards.describe(
        board.id,
        0,
        entries=[
            {"title": "第一镜", "description": "咖啡"},
            {"title": "第二镜", "description": "店员"},
        ],
    )
    first, second = [s.id for s in board.state.shots]
    shots.generate(first, 0, "先完成第一镜")

    def unavailable(*_):
        raise ShotModelError("暂时失败")

    pictures.generate = unavailable

    def choose(index, messages):
        if index == 0:
            return [call("draw_shot", shotId=second, instruction="补画第二镜", reason="补齐")]
        if index == 1:
            assert "暂时失败" in messages[-1]["content"]
            pictures.generate = lambda *_: (SVG, {}, "fixture")
            return [call("draw_shot", shotId=second, instruction="补画第二镜", reason="错误恢复")]
        return [call("finish_task", summary="已补齐", shotIds=[first, second], expectedCount=2)]

    run = StoryboardAgentService(boards, shots, Decisions(choose), runs).start(
        board.id, board.version, "继续补齐没有完成的镜头", background=False
    )
    assert run.status == "completed"
    assert len(shots.get(first).revisions) == len(shots.get(second).revisions) == 1
    assert [s.status for s in run.steps] == ["failed", "succeeded", "succeeded"]


def test_agent_api_returns_run_and_real_board(setup):
    boards, shots, _, runs = setup
    board = boards.create("接口")
    service = StoryboardAgentService(boards, shots, Decisions(lambda *_: []), runs)
    app = FastAPI()
    app.include_router(create_agent_router(lambda: service))
    with TestClient(app) as client:
        assert client.get(f"/api/storyboards/{board.id}/agent/run").json()["run"] is None
        response = client.post(
            f"/api/storyboards/{board.id}/agent/runs",
            json={"expectedVersion": 0, "request": "看看"},
        )
        assert response.status_code == 202
        assert response.json()["board"]["shots"][0]["durationSeconds"] is None
        assert (
            client.post(
                f"/api/storyboards/{board.id}/agent/runs",
                json={"expectedVersion": 99, "request": "看看"},
            ).status_code
            == 409
        )


def test_adapter_sends_real_tools_and_parses_tool_calls():
    def respond(request):
        body = json.loads(request.content)
        assert body["tool_choice"] == "auto" and body["reasoning_effort"] == "off"
        assert body["tools"] and body["stream"] is False
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "one",
                                    "function": {"name": "get_storyboard", "arguments": "{}"},
                                }
                            ]
                        },
                    }
                ]
            },
        )

    adapter = OpenAICompatibleStoryboardAgent(
        ShotModelConfig("https://example.test/v1", "fixture", reasoning_effort="off"),
        httpx.MockTransport(respond),
    )
    result, _ = adapter.decide([], [{"type": "function"}])
    assert result.calls[0].name == "get_storyboard"


def test_cannot_hide_unfinished_created_shots_with_empty_delivery(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("完整交付")

    def choose(index, messages):
        if index == 0:
            return [
                call(
                    "create_shots",
                    shots=[
                        {
                            "title": "尚未绘制",
                            "description": "需要真正完成的画面",
                            "durationSeconds": 5,
                        }
                    ],
                )
            ]
        if index == 1:
            return [call("finish_task", summary="没有画面却声称完成")]
        assert "遗漏" in messages[-1]["content"]
        return [call("finish_task", summary="还有未完成镜头", unresolved=["画面尚未生成"])]

    run = StoryboardAgentService(boards, shots, Decisions(choose), runs).start(
        board.id, 0, "完成分镜", background=False
    )
    assert run.status == "needs_input" and run.steps[1].status == "failed"
    assert not pictures.calls


def test_metadata_edit_preserves_selected_shot_and_duration_check(setup):
    boards, shots, pictures, runs = setup
    board = boards.create("拍摄说明")
    board = boards.change(board.id, 0, "add")
    selected = board.active_id
    board = boards.describe(board.id, board.version, context="暖色")
    assert board.active_id == selected
    board = boards.describe(
        board.id,
        board.version,
        entries=[
            {
                "title": "递杯",
                "description": "双手接杯",
                "durationSeconds": 5,
                "camera": "中景",
            }
        ],
        target_id=selected,
    )
    shots.generate(selected, 0, "咖啡")

    def choose(index, messages):
        if index == 0:
            return [
                call(
                    "finish_task",
                    summary="时长错误",
                    shotIds=[selected],
                    expectedCount=1,
                    expectedDuration=15,
                )
            ]
        assert "总时长" in messages[-1]["content"]
        return [
            call(
                "finish_task",
                summary="五秒镜头",
                shotIds=[selected],
                expectedCount=1,
                expectedDuration=5,
            )
        ]

    run = StoryboardAgentService(boards, shots, Decisions(choose), runs).start(
        board.id, board.version, "查看", background=False
    )
    assert run.status == "completed" and run.steps[0].status == "failed"


@pytest.mark.parametrize("body", [None, {}, {"choices": [{"finish_reason": "length"}]}])
def test_adapter_invalid_output_never_exposes_raw_response(body):
    adapter = OpenAICompatibleStoryboardAgent(
        ShotModelConfig("https://example.test/v1", "fixture", api_key="secret"),
        httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    with pytest.raises(ShotModelError) as caught:
        adapter.decide([], [])
    assert "secret" not in str(caught.value)
