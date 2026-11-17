"""文字直接编辑不调用模型，保持语义对象、版本历史与源码边界。"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicecanvas.api.shots import create_shot_router
from voicecanvas.application.shot_service import ShotConflict, ShotService
from voicecanvas.domain.svg_document import validate_svg
from voicecanvas.domain.svg_text import list_text_blocks, replace_text_block
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
<g id="background"><rect width="1280" height="720" fill="navy"/></g>
<g id="dialogue"><rect x="20" y="20" width="500" height="150" fill="white"/>
<text x="270" y="70" font-size="32" text-anchor="middle">别急，</text>
<text x="270" y="112" font-size="32" text-anchor="middle">我陪你等雨停。</text></g>
<g id="subtitle"><text id="caption" x="640" y="680" font-size="24">雨还没停。</text></g></svg>"""


def test_multiline_blocks_keep_indices_and_preserve_unrelated_objects():
    source = validate_svg(SVG)
    blocks = list_text_blocks(source)
    assert [(b["index"], b["indices"], b["text"]) for b in blocks] == [
        (0, [0, 1], "别急，\n我陪你等雨停。"),
        (2, [2], "雨还没停。"),
    ]
    edited = replace_text_block(source, 0, ["别急，", "我们一起回家。"], 30, 1.4, 72)
    assert "我陪你等雨停。" not in edited
    assert list_text_blocks(edited)[0]["text"] == "别急，\n我们一起回家。"
    for group in ("background", "subtitle"):

        def extract(svg, group=group):
            return next(ET.tostring(e) for e in ET.fromstring(svg).iter() if e.get("id") == group)

        assert extract(source) == extract(edited)
    assert len(ET.fromstring(edited).findall(".//{*}text")) == 2


def test_edit_is_text_not_markup_and_overrides_only_font_size_style():
    source = validate_svg(
        SVG.replace('id="caption"', 'id="caption" style="font-size:24px;fill:gold"')
    )
    edited = replace_text_block(source, 2, ["妈妈 & <script>“到家了吗？”"], 28, 1.35, 680)
    node = next(e for e in ET.fromstring(edited).iter() if e.get("id") == "caption")
    assert "".join(node.itertext()) == "妈妈 & <script>“到家了吗？”"
    assert "font-size" not in node.attrib["style"]
    assert "fill:gold" in node.attrib["style"]
    assert node.get("font-size") == "28"
    assert not ET.fromstring(edited).findall(".//{*}script")


@pytest.mark.parametrize(
    "content",
    [
        '<text x="1 2" y="20">独立定位</text>',
        '<text textLength="100">特殊字距</text>',
        '<text><tspan fill="red">混合样式</tspan></text>',
        '<defs><text id="template">定义</text></defs>',
        '<g id="shared"><text>共享</text></g><use href="#shared"/>',
    ],
)
def test_special_text_is_listed_but_cannot_be_flattened(content):
    source = validate_svg(SVG.replace("</svg>", content + "</svg>"))
    block = list_text_blocks(source)[-1]
    assert not block["editable"] and block["reason"]
    with pytest.raises(ValueError):
        replace_text_block(source, block["index"], ["新内容"], 24, 1.35, 30)


@pytest.mark.parametrize(
    "lines,size,height,y",
    [
        ([], 24, 1.35, 30),
        ([" "], 24, 1.35, 30),
        (["x" * 2001], 24, 1.35, 30),
        (["a\nb"], 24, 1.35, 30),
        (["x"], float("nan"), 1.35, 30),
        (["x"], 24, float("inf"), 30),
        (["x"], 24, 1.35, float("inf")),
        (["x"], 7, 1.35, 30),
        (["x"], 24, 0.5, 30),
    ],
)
def test_invalid_layout_rejected(lines, size, height, y):
    with pytest.raises(ValueError):
        replace_text_block(validate_svg(SVG), 0, lines, size, height, y)


class InitialOnlyGenerator:
    def __init__(self):
        self.calls = 0

    def generate(self, instruction, current_svg):
        self.calls += 1
        assert current_svg is None, "文字编辑不应调用模型"
        return SVG, {}, "fixture"


@pytest.fixture
def ready(tmp_path):
    generator = InitialOnlyGenerator()
    repository = SQLiteShotRepository(tmp_path / "text.sqlite3")
    service = ShotService(repository, generator)
    shot = service.create("文字镜头")
    shot = service.generate(shot.id, 0, "初稿")
    return service, shot, generator


def test_text_revision_survives_reload_history_and_branch(ready):
    service, shot, generator = ready
    changed = service.edit_text(shot.id, 1, 0, ["一起回家。"], 30, 1.35, 90)
    assert changed.revisions[-1].model is None and changed.revisions[-1].usage == {}
    assert generator.calls == 1
    assert service.get(shot.id).svg == changed.svg
    undone = service.move(shot.id, 2, -1)
    assert undone.svg == shot.svg
    redone = service.move(shot.id, 3, 1)
    assert redone.svg == changed.svg
    service.move(shot.id, 4, -1)
    branched = service.edit_text(shot.id, 5, 2, ["新的字幕。"], 26, 1.35, 680)
    assert len(branched.revisions) == 2 and not list_text_blocks(branched.svg)[0][
        "text"
    ].startswith("一起")
    with pytest.raises(ShotConflict):
        service.edit_text(shot.id, 5, 0, ["旧页面"], 24, 1.35, 80)
    assert service.get(shot.id).svg == branched.svg


def test_text_api_validates_and_preserves_failed_version(ready):
    service, shot, generator = ready
    app = FastAPI()
    app.include_router(create_shot_router(lambda: service))
    with TestClient(app) as client:
        state = client.get(f"/api/shots/{shot.id}").json()
        assert state["texts"][0]["text"] == "别急，\n我陪你等雨停。"
        payload = {
            "expectedVersion": 1,
            "index": 0,
            "lines": ["热汤带回来了。"],
            "fontSize": 28,
            "lineHeight": 1.35,
            "y": 90,
        }
        assert (
            client.post(f"/api/shots/{shot.id}/text", json={**payload, "lines": [" "]}).status_code
            == 422
        )
        response = client.post(f"/api/shots/{shot.id}/text", json=payload)
        assert response.status_code == 200 and response.json()["version"] == 2
        assert client.post(f"/api/shots/{shot.id}/text", json=payload).status_code == 409
        assert service.get(shot.id).version == 2 and generator.calls == 1


@pytest.mark.parametrize("name", ["street-edited", "phone-edited", "dialogue"])
def test_real_storyboard_multiline_text_can_be_edited(name):
    sample = Path(__file__).resolve().parents[2] / "docs/experiments/storyboard-text-20261117"
    source = validate_svg((sample / f"{name}.svg").read_text(encoding="utf-8"))
    block = next(b for b in list_text_blocks(source) if "\n" in b["text"])
    edited = replace_text_block(source, block["index"], ["第一行。", "第二行。”"], 24, 1.35, 100)
    assert (
        next(b for b in list_text_blocks(edited) if b["index"] == block["index"])["text"]
        == "第一行。\n第二行。”"
    )
