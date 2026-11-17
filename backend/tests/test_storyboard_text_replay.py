"""回放真实分镜文字响应，验证文案、持久化及改字后的撤销重做。"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import pytest

from voicecanvas.adapters.llm.svg_shot import OpenAICompatibleShotGenerator, ShotModelConfig
from voicecanvas.application.shot_service import ShotService
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository

SAMPLES = Path(__file__).resolve().parents[2] / "docs/experiments/storyboard-text-20261117"


def _text(svg: str) -> str:
    text = "".join(
        "".join(element.itertext())
        for element in ET.fromstring(svg).iter()
        if element.tag.endswith("}text")
    )
    return "".join(text.split())


@pytest.mark.parametrize("name", ["street", "phone", "dialogue"])
def test_real_storyboard_text_survives_edit_and_history(name: str, tmp_path: Path) -> None:
    cases = json.loads((SAMPLES / "cases.json").read_text(encoding="utf-8"))
    case = next(item for item in cases if item["name"] == name)
    labels = [name] + ([f"{name}-edited"] if "edit" in case else [])
    responses = iter(labels)

    def handler(request: httpx.Request) -> httpx.Response:
        label = next(responses)
        record = json.loads((SAMPLES / f"{label}-call.json").read_text(encoding="utf-8"))
        assert record["finish"] == "stop"
        # 回放真实最终输出，不访问供应商，也不把 usage 的嵌套字段绕过产品解析。
        return httpx.Response(
            200,
            json={
                "model": record["returnedModel"],
                "usage": record["usage"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "content": (SAMPLES / f"{label}-response.txt").read_text(
                                encoding="utf-8"
                            )
                        },
                    }
                ],
            },
        )

    generator = OpenAICompatibleShotGenerator(
        ShotModelConfig(base_url="https://replay.invalid/v1", model="deepseek/deepseek-v4.1-flash"),
        transport=httpx.MockTransport(handler),
    )
    database = tmp_path / "shots.sqlite3"
    service = ShotService(SQLiteShotRepository(database), generator)
    shot = service.create(name)
    shot = service.generate(shot.id, shot.version, case["instruction"])
    initial = (SAMPLES / f"{name}.svg").read_text(encoding="utf-8")
    assert shot.svg == initial
    assert all("".join(text.split()) in _text(initial) for text in case["expected"])
    assert ShotService(SQLiteShotRepository(database), generator).get(shot.id).svg == initial

    if "edit" not in case:
        return
    shot = service.generate(shot.id, shot.version, case["edit"])
    edited = (SAMPLES / f"{name}-edited.svg").read_text(encoding="utf-8")
    assert shot.svg == edited
    assert all("".join(text.split()) in _text(edited) for text in case["editedExpected"])
    removed = [text for text in case["expected"] if text not in case["editedExpected"]]
    assert all("".join(text.split()) not in _text(edited) for text in removed)

    protected = (
        ["storefront", "girl", "friend", "subtitle"]
        if name == "street"
        else ["hand-back", "fingertips", "msg-in", "typing", "thumb", "shot-label"]
    )

    def groups(svg: str) -> dict[str, str]:
        return {
            node.attrib["id"]: ET.tostring(node, encoding="unicode")
            for node in ET.fromstring(svg).iter()
            if node.tag.endswith("}g") and "id" in node.attrib
        }

    before, after = groups(initial), groups(edited)
    assert all(before[group] == after[group] for group in protected)
    shot = service.move(shot.id, shot.version, -1)
    assert shot.svg == initial
    shot = service.move(shot.id, shot.version, 1)
    assert shot.svg == edited
    assert ShotService(SQLiteShotRepository(database), generator).get(shot.id).svg == edited
