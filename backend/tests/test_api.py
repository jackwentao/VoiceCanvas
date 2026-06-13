from fastapi.testclient import TestClient

from voicecanvas.api.main import create_app
from voicecanvas.application.orchestration_service import OrchestrationService


def _client() -> TestClient:
    return TestClient(create_app(OrchestrationService()))


def test_health_endpoint() -> None:
    client = _client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voicecanvas-backend"}


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
