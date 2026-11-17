"""验证项目 Agent 实际加载 skill；不是检查 Codex 个人目录。"""

import json

import httpx
import pytest

from voicecanvas.adapters.llm.drawing_skills import load_drawing_skill
from voicecanvas.adapters.llm.svg_shot import (
    DRAW_PROMPT,
    EDIT_PROMPT,
    OpenAICompatibleShotGenerator,
    ShotModelConfig,
)
from voicecanvas.infrastructure.shot_factory import create_shot_service

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
    '<rect id="sky" width="1280" height="720" fill="blue" /></svg>'
)


def test_skill_reaches_real_generation_and_editing_requests():
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        content = (
            SVG
            if len(requests) == 1
            else json.dumps({"edits": [{"old": 'fill="blue"', "new": 'fill="navy"'}]})
        )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
        )

    generator = OpenAICompatibleShotGenerator(
        ShotModelConfig("https://example.test/v1", "test"), httpx.MockTransport(handler)
    )
    generated, _, _ = generator.generate("水彩风格，只画蓝色背景", None)
    edited, _, _ = generator.generate("只把背景改深", generated)
    skill = load_drawing_skill("svg-illustration")
    draw_system = requests[0]["messages"][0]["content"]
    edit_system = requests[1]["messages"][0]["content"]
    assert skill.draw in draw_system and skill.edit not in draw_system
    assert skill.edit in edit_system and skill.draw not in edit_system
    assert draw_system.endswith(DRAW_PROMPT) and edit_system.endswith(EDIT_PROMPT)
    assert requests[0]["messages"][1]["content"] == "水彩风格，只画蓝色背景"
    assert json.loads(requests[1]["messages"][1]["content"])["svg"] == generated
    assert 'fill="navy"' in edited
    assert len(requests) == 2  # 不因加载 skill 额外调用规划或自评模型。


def test_none_disables_skill_and_keeps_base_protocol():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": SVG}, "finish_reason": "stop"}]}
        )

    generator = OpenAICompatibleShotGenerator(
        ShotModelConfig("https://example.test/v1", "test", drawing_skill="none"),
        httpx.MockTransport(handler),
    )
    generator.generate("draw", None)
    assert generator.drawing_skill is None
    assert captured[0]["messages"][0]["content"] == DRAW_PROMPT


@pytest.mark.parametrize("name", ["../../secret", "/tmp/custom.md", "unreviewed-skill", ""])
def test_only_reviewed_builtin_names_can_be_loaded(name):
    with pytest.raises(ValueError, match="未知"):
        load_drawing_skill(name)


def test_factory_selects_skill_from_backend_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICECANVAS_SHOT_DB_PATH", str(tmp_path / "shots.db"))
    monkeypatch.setenv("VOICECANVAS_SHOT_DRAWING_SKILL", "none")
    assert create_shot_service().generator.drawing_skill is None
    monkeypatch.setenv("VOICECANVAS_SHOT_DRAWING_SKILL", "svg-illustration")
    assert create_shot_service().generator.drawing_skill.name == "svg-illustration"
    monkeypatch.setenv("VOICECANVAS_SHOT_DRAWING_SKILL", "bad-setting")
    with pytest.raises(ValueError, match="未知"):
        create_shot_service()


def test_loads_packaged_resources_independent_of_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill = load_drawing_skill("svg-illustration")
    assert skill.name == "svg-illustration"
    assert 0 < len(skill.draw) <= 4000 and 0 < len(skill.edit) <= 4000


@pytest.mark.parametrize(
    "source",
    [
        "",
        "<!-- runtime:draw -->text<!-- /runtime:draw -->",
        "<!-- runtime:draw --><!-- /runtime:draw --><!-- runtime:edit -->ok<!-- /runtime:edit -->",
        "<!-- runtime:draw -->" + "x" * 4001 + "<!-- /runtime:draw -->"
        "<!-- runtime:edit -->ok<!-- /runtime:edit -->",
    ],
)
def test_invalid_skill_resources_fail_before_paid_request(tmp_path, monkeypatch, source):
    resource = tmp_path / "skills/svg_illustration/SKILL.md"
    resource.parent.mkdir(parents=True)
    resource.write_text(source, encoding="utf-8")
    monkeypatch.setattr("voicecanvas.adapters.llm.drawing_skills.files", lambda _: tmp_path)
    with pytest.raises(ValueError):
        OpenAICompatibleShotGenerator(ShotModelConfig("https://example.test/v1", "test"))


def test_missing_builtin_file_is_an_explicit_configuration_error(tmp_path, monkeypatch):
    monkeypatch.setattr("voicecanvas.adapters.llm.drawing_skills.files", lambda _: tmp_path)
    with pytest.raises(ValueError, match="文件缺失"):
        load_drawing_skill("svg-illustration")
