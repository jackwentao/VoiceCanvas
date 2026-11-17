"""真实 PNG 协议、版本隔离、视觉输入和 Agent 自主工具选择的离线回归。"""

import base64
import json
import struct
import zlib

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicecanvas.adapters.llm.storyboard_agent import OpenAICompatibleStoryboardAgent
from voicecanvas.adapters.llm.svg_shot import ShotModelConfig
from voicecanvas.adapters.rendering.chromium import ChromiumShotRenderer
from voicecanvas.api.storyboard_agent import create_agent_router
from voicecanvas.application.shot_service import ShotConflict, ShotModelError, ShotService
from voicecanvas.application.shot_visual_service import ShotVisualService
from voicecanvas.application.storyboard_agent_service import StoryboardAgentService
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.domain.shot_preview import png_dimensions
from voicecanvas.domain.storyboard_agent import AgentDecision, AgentToolCall
from voicecanvas.infrastructure.file_preview_store import FilePreviewStore
from voicecanvas.infrastructure.sqlite_agent_run_repository import SQLiteAgentRunRepository
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository
from voicecanvas.infrastructure.sqlite_storyboard_repository import SQLiteStoryboardRepository

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><circle r="20"/></svg>'


def png(width=1280, height=720):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * width * 3) * height))
        + chunk(b"IEND", b"")
    )


class Renderer:
    identity = "test-renderer"

    def __init__(self):
        self.calls = []

    def render(self, source):
        self.calls.append(source)
        return png()


class Reviewer:
    def __init__(self):
        self.calls = []

    def review_image(self, image, brief, focus=""):
        self.calls.append((image, brief, focus))
        return "女孩手掌没有接触杯柄，需要修正右手。", {"total_tokens": 20}


class Generator:
    def generate(self, *_):
        return SVG, {}, "fixture"


class Decisions:
    def __init__(self, choose):
        self.choose = choose
        self.index = 0

    def decide(self, messages, tools):
        result = self.choose(self.index, messages)
        self.index += 1
        return AgentDecision(
            calls=[
                AgentToolCall(
                    id=f"call_{self.index}",
                    name=name,
                    arguments=args,
                )
                for name, args in result
            ]
        ), {"total_tokens": 1}


@pytest.fixture
def scene(tmp_path):
    db = tmp_path / "boards.sqlite3"
    boards = StoryboardService(SQLiteStoryboardRepository(db))
    shots = ShotService(SQLiteShotRepository(db), Generator())
    board = boards.create("递杯")
    board = boards.describe(
        board.id,
        0,
        entries=[
            {
                "title": "接咖啡",
                "description": "女孩右手握住杯柄",
                "camera": "中景",
                "durationSeconds": 5,
            }
        ],
    )
    shots.generate(board.active_id, 0, "原图")
    renderer, reviewer = Renderer(), Reviewer()
    visual = ShotVisualService(boards, shots, renderer, FilePreviewStore(tmp_path / "previews"))
    return boards, shots, board, renderer, reviewer, visual, SQLiteAgentRunRepository(db)


def test_preview_binds_version_and_caches_exact_pixels(scene):
    boards, shots, board, renderer, _, visual, _ = scene
    result = visual.render(board.id, board.active_id)
    assert result["shotVersion"] == 1 and result["visualReview"] == "rendered_only"
    assert png_dimensions(visual.read(board.id, board.active_id, result["imageId"])) == (1280, 720)
    assert visual.render(board.id, board.active_id) == result
    assert len(renderer.calls) == 1
    shots.generate(board.active_id, 1, "修改")
    with pytest.raises(ShotConflict, match="版本"):
        visual.read(board.id, board.active_id, result["imageId"])
    assert len(renderer.calls) == 1, "过期 GET 不应隐式启动浏览器渲染"
    assert visual.render(board.id, board.active_id)["imageId"] != result["imageId"]


def test_foreign_blank_invalid_image_and_paths_rejected_before_render(scene, tmp_path):
    boards, shots, board, renderer, _, visual, _ = scene
    foreign = boards.create("其他项目")
    with pytest.raises(ValueError, match="不属于"):
        visual.render(board.id, foreign.active_id)
    with pytest.raises(ValueError, match="没有画面"):
        visual.render(foreign.id, foreign.active_id)
    assert not renderer.calls
    with pytest.raises(ValueError, match="标识"):
        FilePreviewStore(tmp_path).put("../x", png())
    renderer.render = lambda _: b"not a PNG"
    with pytest.raises(ValueError, match="有效 PNG"):
        visual.render(board.id, board.active_id)
    renderer.render = lambda _: png(10, 10)
    with pytest.raises(ValueError, match="尺寸"):
        visual.render(board.id, board.active_id)


def test_changed_while_rendering_never_claims_current_preview(scene):
    _, shots, board, renderer, _, visual, _ = scene

    def render(source):
        shots.generate(board.active_id, 1, "另页修改")
        return png()

    renderer.render = render
    with pytest.raises(ShotConflict, match="渲染期间"):
        visual.render(board.id, board.active_id)


def test_changed_while_reading_never_returns_stale_pixels(scene):
    _, shots, board, _, _, visual, _ = scene
    result = visual.render(board.id, board.active_id)
    read = visual.store.get

    def changed(image_id):
        image = read(image_id)
        shots.generate(board.active_id, 1, "另页更新")
        return image

    visual.store.get = changed
    with pytest.raises(ShotConflict, match="读取期间"):
        visual.read(board.id, board.active_id, result["imageId"])


def test_agent_can_review_directly_without_forced_render_tool_and_reuses_preview(scene):
    boards, shots, board, renderer, reviewer, visual, runs = scene

    def choose(index, messages):
        if index < 2:
            return [("review_shot", {"shotId": board.active_id, "focus": "手与杯柄接触关系"})]
        assert "没有接触" in messages[-1]["content"]
        return [("finish_task", {"summary": "评审完成，手需要修改", "unresolved": ["手部动作"]})]

    run = StoryboardAgentService(
        boards,
        shots,
        Decisions(choose),
        runs,
        visual,
        reviewer,
    ).start(board.id, board.version, "先看图评审，不修改", background=False)
    assert run.status == "needs_input" and len(reviewer.calls) == len(renderer.calls) == 1
    assert run.steps[1].result["cached"] is True
    assert run.steps[0].result["requiresUserAcceptance"] is True
    assert run.steps[0].result["shotVersion"] == 1
    assert reviewer.calls[0][0] == png()
    assert "女孩右手握住杯柄" in reviewer.calls[0][1]
    assert run.usage["total_tokens"] == 23
    assert len(shots.get(board.active_id).revisions) == 1
    assert "data:image" not in runs.get_run(run.id).model_dump_json()


def test_render_tool_passes_real_image_to_next_decision_without_base64_in_progress(scene):
    boards, shots, board, _, reviewer, visual, runs = scene

    def choose(index, messages):
        if index == 0:
            return [("render_shot", {"shotId": board.active_id})]
        part = messages[-1]["content"][1]
        assert base64.b64decode(part["image_url"]["url"].split(",")[1]) == png()
        return [("finish_task", {"summary": "预览已返回"})]

    run = StoryboardAgentService(
        boards,
        shots,
        Decisions(choose),
        runs,
        visual,
        reviewer,
    ).start(board.id, board.version, "渲染看看", background=False)
    assert run.status == "completed" and not reviewer.calls
    assert "data:image" not in run.model_dump_json()


def test_review_failure_and_budget_are_visible_without_drawing(scene):
    boards, shots, board, _, reviewer, visual, runs = scene

    def unavailable(*_):
        raise ShotModelError("模型暂不支持图片")

    reviewer.review_image = unavailable

    def choose(index, messages):
        if index < 3:
            return [("review_shot", {"shotId": board.active_id, "focus": f"检查{index}"})]
        assert "每镜两次" in messages[-1]["content"]
        return [("finish_task", {"summary": "视觉不可用", "unresolved": ["等待检查"]})]

    run = StoryboardAgentService(
        boards,
        shots,
        Decisions(choose),
        runs,
        visual,
        reviewer,
    ).start(board.id, board.version, "评审", background=False)
    assert all(s.status == "failed" for s in run.steps[:3])
    assert "模型暂不支持图片" in run.steps[0].result["error"]
    assert len(shots.get(board.active_id).revisions) == 1


def test_preview_api_has_no_side_effects_and_rejects_stale_or_foreign(scene):
    boards, shots, board, renderer, reviewer, visual, runs = scene
    service = StoryboardAgentService(
        boards, shots, Decisions(lambda *_: []), runs, visual, reviewer
    )
    result = visual.render(board.id, board.active_id)
    app = FastAPI()
    app.include_router(create_agent_router(lambda: service))
    with TestClient(app) as client:
        reply = client.get(result["previewUrl"])
        assert reply.status_code == 200 and reply.content == png()
        assert reply.headers["content-type"] == "image/png"
        assert reply.headers["cache-control"] == "no-store"
        assert client.get(result["previewUrl"].replace(result["imageId"], "x")).status_code == 409
        shots.generate(board.active_id, 1, "另一页修改")
        assert client.get(result["previewUrl"]).status_code == 409
    assert len(renderer.calls) == 1


def test_reviewer_uses_same_model_real_image_and_no_svg_or_other_provider():
    def respond(request):
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek/deepseek-v4.1-flash"
        assert payload["reasoning_effort"] == "off"
        assert "tools" not in payload
        content = payload["messages"][1]["content"]
        assert "<svg" not in content[0]["text"]
        assert base64.b64decode(content[1]["image_url"]["url"].split(",")[1]) == png()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "右手与杯子没有接触。"},
                    }
                ],
                "usage": {"total_tokens": 15},
            },
        )

    adapter = OpenAICompatibleStoryboardAgent(
        ShotModelConfig(
            "https://example.test/v1", "deepseek/deepseek-v4.1-flash", reasoning_effort="off"
        ),
        httpx.MockTransport(respond),
    )
    review, usage = adapter.review_image(png(), "接杯动作", "接触关系")
    assert "没有接触" in review and usage["total_tokens"] == 15


@pytest.mark.parametrize("finish,content", [("length", "截断"), ("stop", ""), ("stop", [])])
def test_incomplete_review_never_marked_observed(finish, content):
    adapter = OpenAICompatibleStoryboardAgent(
        ShotModelConfig("https://example.test/v1", "fixture"),
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": finish,
                            "message": {"content": content},
                        }
                    ]
                },
            )
        ),
    )
    with pytest.raises(ShotModelError):
        adapter.review_image(png(), "测试")


def test_renderer_checks_svg_before_starting_external_process(tmp_path):
    renderer = ChromiumShotRenderer(tmp_path, browser_path="missing-executable")
    with pytest.raises(ValueError):
        renderer.render(SVG.replace("<circle", "<script"))
    with pytest.raises(ShotModelError, match="启动"):
        renderer.render(SVG)
