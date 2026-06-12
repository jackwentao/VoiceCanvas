from fastapi.testclient import TestClient

from voicecanvas.api.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voicecanvas-backend"}


def test_start_orchestration_returns_real_project_patches_and_history() -> None:
    client = TestClient(create_app())

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


def test_orchestration_api_keeps_project_state_between_calls() -> None:
    client = TestClient(create_app())
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
