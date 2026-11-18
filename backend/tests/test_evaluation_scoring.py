import json
from pathlib import Path

import httpx
import pytest

from voicecanvas.adapters.llm.svg_shot import ShotModelConfig


@pytest.mark.parametrize("returned_id", ["V1", "P4"])
def test_visual_scoring_keeps_deterministic_checks_out_of_model(tmp_path, monkeypatch, returned_id):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from evaluation.score_visuals import score_case

    case = {
        "criteria": [
            {"id": "V1", "group": "画面", "requirement": "画中有人"},
            {"id": "P4", "group": "保留项", "requirement": "镜头 ID 不变", "visual": False},
        ]
    }
    (tmp_path / "result.json").write_text(json.dumps({
        "run": {"id": "run_one", "request": "画一个人", "summary": "已经通过"},
        "board": {"shots": [{"svg": "<svg/>"}]},
    }), encoding="utf-8")
    archive = Path(__file__).resolve().parents[2] / "docs" / "experiments"
    png = archive / "evaluation-pilot-20261118" / "evidence" / "VC-01" / "shot-01.png"
    (tmp_path / "shot-01.png").write_bytes(png.read_bytes())

    def respond(request):
        payload = json.loads(request.content)
        assert payload["model"] == config.model
        assert payload["temperature"] == 0
        parts = payload["messages"][1]["content"]
        assert json.loads(parts[0]["text"]) == {
            "request": "画一个人", "criteria": [{"id": "V1", "requirement": "画中有人"}],
        }
        assert parts[-1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({"criteria": [
                {"id": returned_id, "status": "pass", "note": "画面中央有人"}
            ]})},
        }]})

    config = ShotModelConfig("https://example.test", "deepseek/deepseek-v4.1-flash", "test-only")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        batch = {"rubricVersion": "pilot-v1"}
        if returned_id == "V1":
            score = score_case(client, config, batch, case, tmp_path)
            assert score["runId"] == "run_one"
            assert score["rubricVersion"] == "pilot-v1"
            assert score["criteria"][0]["status"] == "pass"
        else:
            with pytest.raises(ValueError, match="额外判据"):
                score_case(client, config, batch, case, tmp_path)


def test_visual_scoring_rejects_changed_frozen_criteria(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from evaluation.score_visuals import score_case

    run = {"run": {"id": "run_same", "request": "画一个人"}}
    criteria = [{"id": "V1", "group": "画面", "requirement": "画中有人"}]
    snapshot = {"id": "VC-01", "request": "画一个人", "criteria": criteria}
    case = {"id": "VC-01", "criteria": [{**criteria[0], "requirement": "画中有三个人"}]}
    (tmp_path / "result.json").write_text(json.dumps(run), encoding="utf-8")
    (tmp_path / "case.json").write_text(json.dumps(snapshot), encoding="utf-8")
    config = ShotModelConfig("https://example.test", "deepseek/deepseek-v4.1-flash")
    with pytest.raises(ValueError, match="归档判据与用例快照不一致"):
        score_case(None, config, {"rubricVersion": "v1"}, case, tmp_path)
