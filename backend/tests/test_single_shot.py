"""自由 SVG 镜头闭环，不依赖在线模型或浏览器。"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voicecanvas.adapters.llm.svg_shot import (
    OpenAICompatibleShotGenerator,
    ShotModelConfig,
    ShotModelError,
)
from voicecanvas.api.shots import create_shot_router
from voicecanvas.application.shot_service import ShotConflict, ShotService
from voicecanvas.domain.svg_document import apply_source_edits, validate_svg
from voicecanvas.infrastructure.shot_factory import create_shot_service
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
<defs><linearGradient id="light"><stop offset="0" stop-color="gold"/>
<stop offset="1" stop-color="navy"/></linearGradient></defs>
<g id="sky"><rect width="1280" height="720" fill="url(#light)"/></g>
<g id="cat"><path d="M10 20L30 40Z" fill="orange"/></g></svg>"""


class FakeGenerator:
    def generate(self, instruction, current_svg):
        svg = current_svg.replace('fill="orange"', 'fill="white"') if current_svg else SVG
        return svg, {"total_tokens": 42}, "fake-model"


@pytest.fixture
def service(tmp_path):
    return ShotService(SQLiteShotRepository(tmp_path / "shots.sqlite3"), FakeGenerator())


def test_svg_preserves_free_paths_and_resources():
    svg = validate_svg(SVG)
    assert 'id="cat"' in svg and 'fill="url(#light)"' in svg
    changed = apply_source_edits(svg, [{"old": 'fill="orange"', "new": 'fill="white"'}])
    assert changed.replace('fill="white"', 'fill="orange"') == svg
    assert validate_svg(changed) == changed


@pytest.mark.parametrize(
    "content",
    [
        "<script>alert(1)</script>",
        "<foreignObject/>",
        '<image href="//example.com/x"/>',
        '<rect onload="alert(1)"/>',
        '<use href="missing.svg#x"/>',
        '<rect fill="url(//example.com/x)"/>',
        '<rect id="same"/><rect id="same"/>',
        '<rect fill="url(#missing)"/>',
        "<rect style=\"background:image-set('//x')\"/>",
        '<rect style="fill: u/**/rl(//x)"/>',
        '<rect style="--x:red;fill:var(--x)"/>',
        '<rect style="fill:url(//x)"/>',
        '<rect fill="u/**/rl(//x)"/>',
        '<rect fill="url(&#10;//x&#10;)"/>',
        '<rect xmlns="http://example.com"/>',
    ],
)
def test_svg_rejects_active_or_external_content(content):
    source = SVG.replace("</svg>", content + "</svg>")
    with pytest.raises(ValueError):
        validate_svg(source)


@pytest.mark.parametrize(
    "source",
    [
        '<!DOCTYPE svg [<!ENTITY x "boom">]>' + SVG,
        SVG[:-6],
        SVG.replace("1280 720", "640 480"),
        SVG.replace('<g id="cat">', '<g id="cat">' * 70),
    ],
)
def test_invalid_document(source):
    with pytest.raises(ValueError):
        validate_svg(source)


def test_safe_inline_style():
    assert "style=" in validate_svg(
        SVG.replace('fill="orange"', 'style="fill:rgb(255,120,0);stroke:navy;stroke-width:2"')
    )


def test_patch_batch_is_atomic():
    source = validate_svg(SVG)
    with pytest.raises(ValueError):
        apply_source_edits(
            source,
            [
                {"old": 'fill="orange"', "new": 'fill="white"'},
                {"old": "not-found", "new": "x"},
            ],
        )
    assert 'fill="orange"' in source
    with pytest.raises(ValueError):
        apply_source_edits(source, [{"old": "id=", "new": "class="}])


def test_persistent_lifecycle_and_branch(service):
    shot = service.create("雨夜")
    first = service.generate(shot.id, 0, "画一只猫")
    second = service.generate(shot.id, 1, "猫改成白色")
    assert 'fill="white"' in second.svg
    undone = service.move(shot.id, 2, -1)
    assert undone.svg == first.svg
    redone = service.move(shot.id, 3, 1)
    assert redone.svg == second.svg
    service.move(shot.id, 4, -1)
    branched = service.generate(shot.id, 5, "修改猫")
    assert len(branched.revisions) == 2 and branched.version == 6
    reloaded = SQLiteShotRepository(service.repository.db_path).load(shot.id)
    assert reloaded == branched
    service.move(shot.id, 6, -1)
    blank = service.move(shot.id, 7, -1)
    assert blank.svg is None
    assert service.move(shot.id, 8, 1).svg == first.svg


def test_stale_version_fails_before_calling_model(service):
    shot = service.create("test")
    service.generate(shot.id, 0, "draw")
    with pytest.raises(ShotConflict):
        service.generate(shot.id, 0, "stale")
    assert service.get(shot.id).version == 1


def test_concurrent_undo_during_model_call_cannot_be_overwritten(service):
    shot = service.create("test")
    service.generate(shot.id, 0, "draw")

    class ConcurrentGenerator:
        def generate(self, instruction, current_svg):
            service.move(shot.id, 1, -1)
            return SVG, {}, "fake"

    service.generator = ConcurrentGenerator()
    with pytest.raises(ShotConflict):
        service.generate(shot.id, 1, "slow request")
    assert service.get(shot.id).svg is None
    assert service.get(shot.id).version == 2


def test_invalid_model_result_preserves_good_revision(service):
    shot = service.create("test")
    first = service.generate(shot.id, 0, "draw")

    class InvalidGenerator:
        def generate(self, instruction, current_svg):
            return "<svg>", {}, "fake"

    service.generator = InvalidGenerator()
    with pytest.raises(ValueError):
        service.generate(shot.id, 1, "bad edit")
    assert service.get(shot.id) == first


def test_history_limit_and_edit_after_undo(service):
    shot = service.create("test")
    for version in range(40):
        service.generate(shot.id, version, "draw")
    with pytest.raises(ValueError, match="40"):
        service.generate(shot.id, 40, "one too many")
    service.move(shot.id, 40, -1)
    branched = service.generate(shot.id, 41, "replace last")
    assert len(branched.revisions) == 40 and branched.version == 42


def generator_with_response(content, finish="stop", status=200, streaming=True):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert request.url.path == "/v1/chat/completions"
        if not streaming:
            return httpx.Response(
                status,
                json={"choices": [{"message": {"content": content}, "finish_reason": finish}]},
            )
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "不要作为绘图输出"}}]},
            {"choices": [{"delta": {"content": content}, "finish_reason": finish}]},
            {
                "choices": [],
                "usage": {
                    "total_tokens": 123,
                    "completion_tokens_details": {"reasoning_tokens": 80},
                },
            },
        ]
        body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    return OpenAICompatibleShotGenerator(
        ShotModelConfig("https://example.test/v1", "test", api_key="never-expose-this"),
        httpx.MockTransport(handler),
    )


def test_streaming_generation_counts_reasoning_but_does_not_draw_it():
    svg, usage, model = generator_with_response(SVG).generate("draw", None)
    assert svg == validate_svg(SVG)
    assert usage == {"total_tokens": 123, "reasoning_tokens": 80}
    assert model == "test"


@pytest.mark.parametrize("effort", [None, "off", "low"])
def test_reasoning_effort_is_explicit_and_applies_to_draw_and_edit(effort):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload.get("reasoning_effort") == effort
        assert ("reasoning_effort" in payload) == (effort is not None)
        assert "thinking" not in payload
        content = SVG if len(calls) == 1 else json.dumps({
            "edits": [{"old": 'fill="orange"', "new": 'fill="blue"'}]
        })
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}]
        })

    generator = OpenAICompatibleShotGenerator(
        ShotModelConfig("https://example.test/v1", "test", reasoning_effort=effort),
        httpx.MockTransport(handler),
    )
    drawn = generator.generate("画猫", None)[0]
    assert 'fill="blue"' in generator.generate("改成蓝色", drawn)[0]
    assert len(calls) == 2


def test_reasoning_factory_defaults_to_fast_and_can_use_provider_default(tmp_path, monkeypatch):
    monkeypatch.setattr("voicecanvas.infrastructure.shot_factory.load_dotenv", lambda: None)
    monkeypatch.setenv("VOICECANVAS_SHOT_DB_PATH", str(tmp_path / "shots.sqlite3"))
    monkeypatch.delenv("VOICECANVAS_SHOT_REASONING_EFFORT", raising=False)
    assert create_shot_service().generator.config.reasoning_effort == "off"
    monkeypatch.setenv("VOICECANVAS_SHOT_REASONING_EFFORT", "provider-default")
    assert create_shot_service().generator.config.reasoning_effort is None
    monkeypatch.setenv("VOICECANVAS_SHOT_REASONING_EFFORT", "unsupported")
    with pytest.raises(ValueError, match="思考强度"):
        create_shot_service()


def test_model_local_edit():
    edits = json.dumps({"edits": [{"old": 'fill="orange"', "new": 'fill="white"'}]})
    svg, _, _ = generator_with_response(edits).generate("白猫", validate_svg(SVG))
    assert 'fill="white"' in svg


@pytest.mark.parametrize("finish", ["length", None, "content_filter"])
def test_partial_model_result_is_never_committed(finish):
    with pytest.raises(ShotModelError):
        generator_with_response(SVG, finish).generate("draw", None)


def test_non_streaming_compatible_provider():
    assert generator_with_response(SVG, streaming=False).generate("draw", None)[0] == validate_svg(
        SVG
    )


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_errors_do_not_expose_credentials(status):
    with pytest.raises(ShotModelError) as error:
        generator_with_response(SVG, status=status).generate("draw", None)
    assert "never-expose-this" not in str(error.value)


@pytest.mark.parametrize("body", ["data: {broken}\n\n", "data: [DONE]\n\n"])
def test_malformed_or_empty_stream(body):
    generator = OpenAICompatibleShotGenerator(
        ShotModelConfig("https://example.test/v1", "test"),
        httpx.MockTransport(
            lambda _: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        ),
    )
    with pytest.raises(ShotModelError):
        generator.generate("draw", None)


def test_transport_timeout_is_actionable():
    def handler(request):
        raise httpx.ReadTimeout("secret internal context", request=request)

    generator = OpenAICompatibleShotGenerator(
        ShotModelConfig("https://example.test/v1", "test"), httpx.MockTransport(handler)
    )
    with pytest.raises(ShotModelError, match="超时") as error:
        generator.generate("draw", None)
    assert "secret" not in str(error.value)


def test_factory_uses_independent_overrides_and_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICECANVAS_SHOT_DB_PATH", str(tmp_path / "shots.sqlite3"))
    monkeypatch.setenv("VOICECANVAS_SHOT_LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("VOICECANVAS_SHOT_LLM_MODEL", "independent-model")
    monkeypatch.setenv("VOICECANVAS_SHOT_LLM_API_KEY", "private-key")
    monkeypatch.setenv("VOICECANVAS_SHOT_MAX_TOKENS", "32768")
    monkeypatch.setenv("VOICECANVAS_SHOT_TIMEOUT_SECONDS", "300")
    service = create_shot_service()
    assert service.repository.db_path == tmp_path / "shots.sqlite3"
    assert service.generator.config.model == "independent-model"
    assert "private-key" not in repr(service.generator.config)
    monkeypatch.setenv("VOICECANVAS_SHOT_MAX_TOKENS", "0")
    with pytest.raises(ValueError):
        create_shot_service()


def test_api_lifecycle_export_and_validation(service):
    app = FastAPI()
    app.include_router(create_shot_router(lambda: service))
    client = TestClient(app)
    created = client.post("/api/shots", json={"title": "雨夜"})
    assert created.status_code == 201
    path = "/api/shots/" + created.json()["id"]
    assert client.get(path + "/export.svg").status_code == 409
    assert (
        client.post(
            path + "/generate", json={"expectedVersion": 0, "instruction": "  "}
        ).status_code
        == 422
    )
    response = client.post(path + "/generate", json={"expectedVersion": 0, "instruction": "画猫"})
    assert response.status_code == 200
    assert response.json()["canUndo"] and not response.json()["canRedo"]
    assert "svg" not in response.json()["revisions"][0]
    assert (
        client.post(
            path + "/generate", json={"expectedVersion": 0, "instruction": "改猫"}
        ).status_code
        == 409
    )
    exported = client.get(path + "/export.svg")
    assert exported.text == response.json()["svg"]
    assert "attachment" in exported.headers["content-disposition"]
    undone = client.post(path + "/undo", json={"expectedVersion": 1}).json()
    assert undone["svg"] is None and undone["canRedo"]
    assert client.post(path + "/redo", json={"expectedVersion": 2}).json()["svg"]
    assert client.get("/api/shots/nonexistent").status_code == 404


def test_optional_local_address_reaches_transport_without_retry(monkeypatch):
    """连接族可配置；沿用证书验证与单次请求，不降级关闭 TLS。"""
    import voicecanvas.adapters.llm.svg_shot as adapter

    options = []
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": SVG}, "finish_reason": "stop"}],
        })

    def transport(**kwargs):
        options.append(kwargs)
        return httpx.MockTransport(handler)

    monkeypatch.setattr(adapter.httpx, "HTTPTransport", transport)
    generator = OpenAICompatibleShotGenerator(
        ShotModelConfig("https://example.test/v1", "test", local_address="::")
    )
    assert generator.generate("画猫", None)[0] == validate_svg(SVG)
    assert options == [{"local_address": "::"}]
    assert len(calls) == 1


def test_factory_local_address_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr("voicecanvas.infrastructure.shot_factory.load_dotenv", lambda: None)
    monkeypatch.setenv("VOICECANVAS_SHOT_DB_PATH", str(tmp_path / "shots.sqlite3"))
    monkeypatch.delenv("VOICECANVAS_SHOT_LOCAL_ADDRESS", raising=False)
    assert create_shot_service().generator.config.local_address is None
    monkeypatch.setenv("VOICECANVAS_SHOT_LOCAL_ADDRESS", "::")
    assert create_shot_service().generator.config.local_address == "::"


def test_api_model_failure_is_502_and_keeps_previous_state(service):
    shot = service.create("test")
    first = service.generate(shot.id, 0, "draw")

    class UnavailableGenerator:
        def generate(self, instruction, current_svg):
            raise ShotModelError("服务暂不可用")

    service.generator = UnavailableGenerator()
    app = FastAPI()
    app.include_router(create_shot_router(lambda: service))
    client = TestClient(app)
    result = client.post(
        f"/api/shots/{shot.id}/generate", json={"expectedVersion": 1, "instruction": "edit"}
    )
    assert result.status_code == 502
    assert service.get(shot.id) == first


@pytest.mark.parametrize(
    "sample_name",
    [
        "rain-baseline",
        "rain-compact",
        "bench-baseline",
        "bench-subject-first",
        "bench-compact",
    ],
)
def test_recorded_model_svgs_survive_streaming_persistence_and_history(service, sample_name):
    """回放实际产物，覆盖自由路径、复杂分组、滤镜和文字的完整保存链路。"""
    sample = (
        Path(__file__).resolve().parents[2]
        / "docs/experiments"
        / "subject-quality-20261117"
        / f"{sample_name}.svg"
    )
    svg = sample.read_text(encoding="utf-8")
    service.generator = generator_with_response(svg)
    shot = service.create(sample_name)
    drawn = service.generate(shot.id, 0, "回放保存的模型响应")
    assert drawn.svg == svg
    # 重新打开连接再读取，不能只验证返回对象中的内容。
    restored = SQLiteShotRepository(service.repository.db_path).load(shot.id)
    assert restored.svg == svg
    assert service.move(shot.id, 1, -1).svg is None
    assert service.move(shot.id, 2, 1).svg == svg
