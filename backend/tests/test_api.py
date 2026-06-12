from fastapi.testclient import TestClient

from voicecanvas.api.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voicecanvas-backend"}


def test_start_orchestration_returns_mock_langgraph_action() -> None:
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
    assert body["nextAction"]["type"] == "EXECUTE_COMMANDS"
    assert body["events"][-1]["type"] == "TURN_SUMMARY"

