import json

from fastapi.testclient import TestClient

from voicecanvas.api.main import create_app
from voicecanvas.application.asset_storage import CatalogAssetContent, CatalogAssetRef
from voicecanvas.application.orchestration_service import OrchestrationService


class FakeAssetStorage:
    def catalog_asset_url(self, path: str) -> CatalogAssetRef:
        if path != "catalog/commerce/food-drink/bubble-tea.png":
            from voicecanvas.application.asset_storage import validate_catalog_asset_path

            validate_catalog_asset_path(path)
        return CatalogAssetRef(
            path=path,
            provider="minio",
            url=f"/api/assets/catalog/raw?path={path}",
        )

    def read_catalog_asset(self, path: str) -> CatalogAssetContent:
        if path != "catalog/commerce/food-drink/bubble-tea.png":
            from voicecanvas.application.asset_storage import validate_catalog_asset_path

            validate_catalog_asset_path(path)
        return CatalogAssetContent(content=b"fake-image", media_type="image/png")


def _client() -> TestClient:
    return TestClient(create_app(OrchestrationService(), asset_storage=FakeAssetStorage()))


def _parse_sse_blocks(text: str) -> list[dict[str, object]]:
    blocks = []
    for raw_block in text.strip().split("\n\n"):
        event_name = None
        data = None
        for line in raw_block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            if line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if event_name and data is not None:
            blocks.append({"event": event_name, "data": data})
    return blocks


def test_health_endpoint() -> None:
    client = _client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voicecanvas-backend"}


def test_default_app_persists_project_state_with_sqlite(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "voicecanvas.sqlite3"
    monkeypatch.setenv("VOICECANVAS_PROJECT_DB_PATH", str(db_path))

    first_client = TestClient(create_app(asset_storage=FakeAssetStorage()))
    first_client.post(
        "/api/projects",
        json={
            "projectId": "project_sqlite_api",
            "title": "SQLite API 项目",
            "mode": "storyboard",
        },
    )
    second_client = TestClient(create_app(asset_storage=FakeAssetStorage()))
    response = second_client.get("/api/projects/project_sqlite_api")

    assert response.status_code == 200
    assert response.json()["project"]["title"] == "SQLite API 项目"


def test_catalog_asset_endpoint_returns_backend_proxy_url() -> None:
    client = _client()

    response = client.get(
        "/api/assets/catalog",
        params={"path": "catalog/commerce/food-drink/bubble-tea.png"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "minio"
    assert body["path"] == "catalog/commerce/food-drink/bubble-tea.png"
    assert body["url"].startswith("/api/assets/catalog/raw")


def test_catalog_asset_endpoint_rejects_unsafe_paths() -> None:
    client = _client()

    for path in ["", "../secret.png", "/catalog/commerce/a.png", "avatar/user.png"]:
        response = client.get("/api/assets/catalog", params={"path": path})
        assert response.status_code in {400, 422}


def test_catalog_asset_raw_endpoint_returns_image_content() -> None:
    client = _client()

    response = client.get(
        "/api/assets/catalog/raw",
        params={"path": "catalog/commerce/food-drink/bubble-tea.png"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == b"fake-image"


def test_create_project_endpoint_returns_blank_project() -> None:
    client = _client()

    response = client.post(
        "/api/projects",
        json={"title": "新建演示项目", "mode": "storyboard"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["project"]["id"].startswith("project_")
    assert body["project"]["title"] == "新建演示项目"
    assert body["project"]["activeSceneId"] == "scene_1"
    assert body["project"]["scenes"][0]["elements"] == []
    assert body["history"] == []
    assert body["events"][-1]["type"] == "PROJECT_CREATED"


def test_start_orchestration_returns_real_project_patches_and_history() -> None:
    client = _client()

    response = client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "创建一个三镜头奶茶带货分镜",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["sessionId"].startswith("session_")
    assert body["status"] == "COMPLETED"
    assert body["project"]["id"] == "project_demo"
    assert len(body["project"]["scenes"]) == 3
    assert body["patches"]
    assert body["history"]
    assert body["nextAction"] is None
    assert any(event["type"] == "CANVAS_PATCH_APPLIED" for event in body["events"])
    assert body["events"][-1]["type"] == "TURN_SUMMARY"


def test_stream_orchestration_returns_sse_events_and_final_result() -> None:
    client = _client()

    response = client.post(
        "/api/orchestrations/stream",
        json={
            "projectId": "project_demo",
            "userInput": "创建一个三镜头的珍珠奶茶带货分镜",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    blocks = _parse_sse_blocks(response.text)
    assert blocks[0]["event"] == "orchestration.event"
    assert blocks[0]["data"]["type"] == "STAGE_CHANGED"

    patch_blocks = [
        block
        for block in blocks
        if block["event"] == "orchestration.event"
        and block["data"]["type"] == "CANVAS_PATCH_APPLIED"
    ]
    assert len(patch_blocks) >= 3
    assert blocks[-1]["event"] == "orchestration.result"
    assert blocks[-1]["data"]["status"] == "COMPLETED"
    assert len(blocks[-1]["data"]["patches"]) == len(patch_blocks)


def test_get_project_returns_backend_project_state_and_history() -> None:
    client = _client()
    client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "加标题，写新品上市",
        },
    )

    response = client.get("/api/projects/project_demo")

    body = response.json()
    assert response.status_code == 200
    assert body["project"]["id"] == "project_demo"
    assert body["history"]
    assert body["events"] == []


def test_export_project_endpoint_returns_reloadable_bundle() -> None:
    client = _client()
    client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "加标题，写新品上市",
        },
    )

    response = client.post(
        "/api/projects/project_demo/export",
        json={"format": "json", "scope": "project"},
    )

    body = response.json()
    exported_payload = json.loads(body["export"]["content"])
    assert response.status_code == 200
    assert body["export"]["filename"].endswith(".voicecanvas.json")
    assert exported_payload["type"] == "voicecanvas.project"
    assert exported_payload["project"]["id"] == "project_demo"


def test_import_project_endpoint_restores_exported_bundle() -> None:
    client = _client()
    exported = client.post(
        "/api/projects/project_demo/export",
        json={"format": "json", "scope": "project"},
    ).json()
    payload = json.loads(exported["export"]["content"])
    payload["project"]["id"] = "project_imported"
    payload["project"]["title"] = "载入后的项目"

    response = client.post("/api/projects/import", json={"payload": payload})

    body = response.json()
    assert response.status_code == 200
    assert body["project"]["id"] == "project_imported"
    assert body["project"]["title"] == "载入后的项目"
    assert body["events"][-1]["type"] == "PROJECT_IMPORTED"


def test_import_project_endpoint_resets_history_for_same_project_id() -> None:
    client = _client()
    client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_reset",
            "userInput": "加标题，写新品上市",
        },
    )
    before = client.get("/api/projects/project_reset").json()
    assert before["history"]

    payload = {
        "type": "voicecanvas.project",
        "schemaVersion": 1,
        "project": {
            "id": "project_reset",
            "title": "重新载入的项目",
            "mode": "storyboard",
            "scenes": [{"id": "scene_1", "name": "空白画布", "order": 1}],
            "activeSceneId": "scene_1",
        },
    }

    response = client.post("/api/projects/import", json={"payload": payload})

    body = response.json()
    assert response.status_code == 200
    assert body["project"]["title"] == "重新载入的项目"
    assert body["history"] == []


def test_import_project_endpoint_rejects_non_project_json() -> None:
    client = _client()

    response = client.post("/api/projects/import", json={"payload": {"hello": "world"}})

    assert response.status_code == 400
    assert "项目 JSON 格式不正确" in response.json()["detail"]


def test_orchestration_api_keeps_project_state_between_calls() -> None:
    client = _client()
    client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "创建一个三镜头奶茶带货分镜",
        },
    )

    response = client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "切换到第二镜头",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["project"]["activeSceneId"] == "scene_demo_2"
    assert body["patches"][-1]["type"] == "ACTIVE_SCENE_CHANGED"


def test_resume_orchestration_accepts_voice_clarification_answer() -> None:
    client = _client()
    client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "创建一个三镜头奶茶带货分镜",
        },
    )
    waiting = client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "把标题放上面",
        },
    ).json()

    response = client.post(
        f"/api/orchestrations/{waiting['sessionId']}/resume",
        json={
            "projectId": "project_demo",
            "answer": "左边那个",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "COMPLETED"
    assert body["patches"][-1]["type"] == "ELEMENT_UPDATED"
    assert body["nextAction"] is None


def test_resume_orchestration_confirms_clear_scene() -> None:
    client = _client()
    client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "加标题，写新品上市",
        },
    )
    waiting = client.post(
        "/api/orchestrations",
        json={
            "projectId": "project_demo",
            "userInput": "清空当前画布",
        },
    ).json()

    response = client.post(
        f"/api/orchestrations/{waiting['sessionId']}/resume",
        json={
            "projectId": "project_demo",
            "answer": "确认清空",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "COMPLETED"
    assert body["patches"][-1]["type"] == "SCENE_CLEARED"
    assert body["project"]["scenes"][0]["elements"] == []
